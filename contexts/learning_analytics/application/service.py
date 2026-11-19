from datetime import datetime

from contexts.learning_analytics.domain.analysis import Profile, StudentAnalysis
from contexts.learning_analytics.domain.ports import AnswerRecord, LearningDataPort
from shared.infrastructure.llm.port import LLMPort

SUBJECTIVE_TYPES = ("short_answer", "scenario", "code")


class LearningAnalyticsService:
    def __init__(self, data: LearningDataPort, llm: LLMPort):
        self._data = data
        self._llm = llm

    def analyze(self, student_id: str) -> StudentAnalysis:
        records = self._data.answer_records(student_id)
        return StudentAnalysis(
            student_id=student_id,
            profile=self._build_profile(student_id, records),
            trend=[],
            weak_points=[],
        )

    def _build_profile(self, student_id: str, records: list[AnswerRecord]) -> Profile:
        correct = sum(1 for r in records if r.is_correct is True)
        graded = sum(1 for r in records if r.is_correct is not None)
        scores = [
            r.score
            for r in records
            if r.question_type in SUBJECTIVE_TYPES and r.score is not None
        ]
        return Profile(
            enrolled_courses=self._data.enrolled_course_count(student_id),
            completed_videos=self._data.completed_video_count(student_id),
            total_videos=self._data.enrolled_video_count(student_id),
            overall_accuracy=(correct / graded) if graded else None,
            subjective_avg_score=(sum(scores) / len(scores)) if scores else None,
            last_active_at=self._last_active_at(student_id, records),
        )

    def _last_active_at(
        self, student_id: str, records: list[AnswerRecord]
    ) -> datetime | None:
        last_completed = self._data.last_completed_at(student_id)
        last_answered = max(
            (r.answered_at for r in records if r.answered_at is not None), default=None
        )
        candidates = [t for t in (last_completed, last_answered) if t is not None]
        return max(candidates) if candidates else None
