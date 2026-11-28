import json
import uuid

from sqlalchemy.orm import Session

from contexts.exam_paper_generation.domain.allocation import allocate_types
from contexts.exam_paper_generation.domain.anchor import (
    blank_code,
    extract_code_blocks,
    has_code_block,
    slice_content_md,
    split_long_interval,
)
from contexts.exam_paper_generation.domain.clean import clean_markdown
from contexts.exam_paper_generation.domain.count import (
    count_for_duration,
    plan_chapter_exam_counts,
    plan_question_counts,
)
from contexts.self_practice.domain.ports import Question
from shared.infrastructure.db.models.sync_cache import Chapter, Video, VideoAnnotation
from shared.infrastructure.llm.port import LLMPort
from shared.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

_SCHEMAS = {
    "multi_choice": '{"content": {"stem": str, "options": [str, str, str, str]}, "reference_answer": {"correct": [str]}, "explanation": str}',
    "short_answer": '{"content": {"stem": str}, "reference_answer": {"points": [str]}, "explanation": str}',
    "scenario": '{"content": {"scenario": str, "task": str}, "reference_answer": {"points": [str]}, "explanation": str}',
}

_CODE_FILL_STEM = "请补全以下代码中被挖空的部分。"

_MULTI_CHOICE_INSTRUCTION = (
    "不定项选择题要求：正确选项数量不固定（1 个或多个），不要全部只设 1 个正确项；"
    "至少一部分题目的正确项应有 2 个及以上。"
    "content.options 按顺序放 4 个选项文本（不带字母），"
    "reference_answer.correct 用选项字母列表表示正确项（如 [\"A\"] 或 [\"A\", \"C\"]）。"
)


def _extract_json_list(content: str) -> list | None:
    """从 LLM 输出中提取题目列表，容忍 ```json 围栏与单对象输出。"""
    text = (content or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return None
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    return None


class QuestionGenerationAdapter:
    def __init__(self, session: Session, llm: LLMPort):
        self._session = session
        self._llm = llm

    def plan_counts(self, video_ids: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for vid in video_ids:
            video = self._session.get(Video, vid)
            if video is None or video.duration_seconds is None:
                continue
            counts[vid] = count_for_duration(video.duration_seconds)
        return counts

    def generate_by_video(self, video_id: str, count: int) -> list[Question]:
        annotation = self._session.get(VideoAnnotation, video_id)
        if annotation is None:
            logger.warning("video_annotation_missing", video_id=video_id)
            return []
        chapter = self._session.get(Chapter, annotation.chapter_id) if annotation.chapter_id else None
        if chapter is None or chapter.content_md is None:
            logger.warning("chapter_content_missing", video_id=video_id)
            return []
        sliced = self._slice(chapter.content_md, annotation)
        if sliced is None:
            logger.warning("anchor_slice_failed", video_id=video_id)
            return []
        text = split_long_interval(sliced)
        has_code = has_code_block(text)
        types = allocate_types(count, has_code)

        questions: list[Question] = []
        for qtype, n in types.items():
            if n <= 0:
                continue
            if qtype == "code_fill":
                questions.extend(self._generate_code_fill(video_id, n, text))
            else:
                questions.extend(self._generate_type(video_id, qtype, n, text))
        return questions

    def generate_from_document(self, course_document: str) -> list[Question]:
        """由前端传入的视频内容直读出题（不查库、不做锚点切片）。

        流程：清洗 courseDocument -> 按长度定题量 -> 分题型 LLM 出题。
        合并出题的题目 video_id 置空（不属于单一视频）。
        """
        full_text = clean_markdown(course_document)
        if not full_text:
            return []

        has_code = has_code_block(full_text, min_lines=15)
        counts = plan_question_counts(len(full_text), has_code)
        text = split_long_interval(full_text)

        questions: list[Question] = []
        for qtype, n in counts.items():
            if n <= 0:
                continue
            if qtype == "code_fill":
                questions.extend(self._generate_code_fill("", n, text))
            else:
                questions.extend(self._generate_type("", qtype, n, text))
        return questions

    def generate_chapter_exam(self, course_document: str) -> list[Question]:
        """章节考试出题：固定 20 不定项 + 5 论述 + 1 代码填空 + 1 场景。

        流程同 generate_from_document，但题量固定；代码填空从融合文本的代码块确定性挖空
        （无代码块时静默跳过）。合并出题 video_id 置空（不属于单一视频）。
        """
        full_text = clean_markdown(course_document)
        if not full_text:
            return []
        counts = plan_chapter_exam_counts()
        text = split_long_interval(full_text)

        questions: list[Question] = []
        for qtype, n in counts.items():
            if n <= 0:
                continue
            if qtype == "code_fill":
                questions.extend(self._generate_code_fill("", n, text))
            else:
                questions.extend(self._generate_type("", qtype, n, text))
        return questions

    def _generate_code_fill(self, video_id: str, n: int, text: str) -> list[Question]:
        """确定性出代码填空题：从课程文档原始代码块中挖空，答案取自原代码。"""
        questions: list[Question] = []
        for block in extract_code_blocks(text):
            if len(questions) >= n:
                break
            code, answers = blank_code(block)
            if not answers:
                continue
            questions.append(
                Question(
                    question_id="q_" + uuid.uuid4().hex[:12],
                    video_id=video_id,
                    question_type="code_fill",
                    content={"stem": _CODE_FILL_STEM, "code": code},
                    reference_answer={"answers": answers},
                    explanation="",
                )
            )
        return questions

    def _generate_type(self, video_id: str, qtype: str, n: int, text: str) -> list[Question]:
        prompt = self._build_prompt(qtype, n, text)
        for _ in range(2):  # 初次 + 重试一次
            result = self._llm.chat(prompt)
            items = _extract_json_list(result.content)
            if items is not None:
                return self._build_questions(video_id, qtype, items)
        logger.warning("question_generation_failed", video_id=video_id, question_type=qtype)
        return []

    def _build_questions(self, video_id: str, qtype: str, items: list) -> list[Question]:
        questions: list[Question] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            questions.append(
                Question(
                    question_id="q_" + uuid.uuid4().hex[:12],
                    video_id=video_id,
                    question_type=qtype,
                    content=item.get("content", {}),
                    reference_answer=item.get("reference_answer", {}),
                    explanation=item.get("explanation", ""),
                )
            )
        return questions

    def _slice(self, content_md: str, annotation: VideoAnnotation) -> str | None:
        sliced = slice_content_md(
            content_md,
            annotation.start_sentence or "",
            annotation.end_sentence or "",
        )
        if sliced is not None:
            return sliced
        fallback = annotation.fallback_range or ""
        if "~" not in fallback:
            return None
        start_marker, end_marker = fallback.split("~", 1)
        return self._slice_by_range(content_md, start_marker.strip(), end_marker.strip())

    def _slice_by_range(self, content_md: str, start_marker: str, end_marker: str) -> str | None:
        if not start_marker or not end_marker:
            return None
        lines = content_md.split("\n")
        start_i: int | None = None
        end_i: int | None = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if start_i is None and stripped.startswith("#") and start_marker in stripped:
                start_i = i
            elif start_i is not None and stripped.startswith("#") and end_marker in stripped:
                end_i = i
                break
        if start_i is None or end_i is None:
            return None
        return "\n".join(lines[start_i : end_i + 1])

    def _build_prompt(self, qtype: str, n: int, text: str) -> list[dict[str, str]]:
        schema = _SCHEMAS.get(qtype, _SCHEMAS["short_answer"])
        instruction = (
            f"下面是课程内容，请基于它生成 {n} 道「{qtype}」题，"
            f"每道题严格按 JSON 结构输出：{schema}。"
            f"题干（stem，场景题对应 task）直接写成完整的问题，"
            f"不要出现「根据课程内容」「根据以上内容」「结合所学」这类前缀。"
            f"课程内容可能存在 OCR 或转写错别字，请按正确语义理解并纠正错字，"
            f"不要将错字照搬进题干、选项或参考答案。"
        )
        if qtype == "multi_choice":
            instruction += f"\n{_MULTI_CHOICE_INSTRUCTION}"
        return [
            {"role": "system", "content": "你是出题 Agent，输出 JSON 数组。"},
            {
                "role": "user",
                "content": instruction + f"\n\n课程内容：\n{text}",
            },
        ]
