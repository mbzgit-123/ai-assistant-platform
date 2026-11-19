import json
import uuid

from sqlalchemy.orm import Session

from contexts.exam_paper_generation.domain.allocation import allocate_types
from contexts.exam_paper_generation.domain.anchor import (
    has_code_block,
    slice_content_md,
    split_long_interval,
)
from contexts.exam_paper_generation.domain.count import count_for_duration
from contexts.self_practice.domain.ports import Question
from shared.infrastructure.db.models.sync_cache import Chapter, Video, VideoAnnotation
from shared.infrastructure.llm.port import LLMPort
from shared.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

_SCHEMAS = {
    "multi_choice": '{"content": {"stem": str, "options": [str, str, str, str]}, "reference_answer": {"correct": [str]}, "explanation": str}',
    "short_answer": '{"content": {"stem": str}, "reference_answer": {"points": [str]}, "explanation": str}',
    "scenario": '{"content": {"scenario": str, "task": str}, "reference_answer": {"points": [str]}, "explanation": str}',
    "code_fill": '{"content": {"stem": str, "code": str}, "reference_answer": {"answers": [str]}, "explanation": str}',
}

_CODE_FILL_INSTRUCTION = (
    "代码填空题要求：从代码块中挑选核心部分（变量名、关键字、关键表达式等）挖空，"
    "不要整段覆盖；挖空处用 ______ 占位，content.code 为挖空后的完整代码，"
    "reference_answer.answers 按顺序列出被挖空的原始内容。"
)


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
            questions.extend(self._generate_type(video_id, qtype, n, text))
        return questions

    def _generate_type(self, video_id: str, qtype: str, n: int, text: str) -> list[Question]:
        prompt = self._build_prompt(qtype, n, text)
        for _ in range(2):  # 初次 + 重试一次
            result = self._llm.chat(prompt)
            try:
                items = json.loads(result.content)
            except (ValueError, TypeError):
                continue
            if isinstance(items, list):
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
            f"根据以下课程内容生成 {n} 道「{qtype}」题，"
            f"每道题严格按 JSON 结构输出：{schema}。"
        )
        if qtype == "code_fill":
            instruction += f"\n{_CODE_FILL_INSTRUCTION}"
        return [
            {"role": "system", "content": "你是出题 Agent，输出 JSON 数组。"},
            {
                "role": "user",
                "content": instruction + f"\n\n课程内容：\n{text}",
            },
        ]
