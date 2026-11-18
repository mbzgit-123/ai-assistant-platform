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
        sliced = slice_content_md(
            chapter.content_md,
            annotation.start_sentence or "",
            annotation.end_sentence or "",
        )
        if sliced is None:
            # v1.0 不解析 fallback_range；坏锚点干净跳过该视频
            logger.warning("anchor_slice_failed", video_id=video_id)
            return []
        text = split_long_interval(sliced)
        has_code = has_code_block(text)
        types = allocate_types(count, has_code)

        questions: list[Question] = []
        for qtype, n in types.items():
            if n <= 0:
                continue
            questions.extend(self._generate_type(video_id, qtype, n))
        return questions

    def _generate_type(self, video_id: str, qtype: str, n: int) -> list[Question]:
        prompt = self._build_prompt(qtype, n)
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

    def _build_prompt(self, qtype: str, n: int) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": "你是出题 Agent，输出 JSON 数组。"},
            {"role": "user", "content": f"生成 {n} 道 {qtype} 题。"},
        ]
