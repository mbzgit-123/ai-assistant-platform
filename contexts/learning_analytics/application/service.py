from datetime import datetime

from contexts.learning_analytics.domain.analysis import (
    MasteryTrendPoint,
    Profile,
    StudentAnalysis,
    WeakPoint,
)
from contexts.learning_analytics.domain.ports import AnswerRecord, LearningDataPort
from shared.infrastructure.llm.port import LLMPort

SUBJECTIVE_TYPES = ("short_answer", "scenario")
WEAK_ACCURACY_THRESHOLD = 0.6
MAX_WEAK_POINTS = 3
WEAK_POINT_SYSTEM_PROMPT = (
    "你是学习分析助手。根据章节正确率，用一句话给出薄弱点归因与改进建议。"
)


class LearningAnalyticsService:
    def __init__(self, data: LearningDataPort, llm: LLMPort):
        self._data = data
        self._llm = llm

    def analyze(self, student_id: str) -> StudentAnalysis:
        records = self._data.answer_records(student_id)
        return StudentAnalysis(
            student_id=student_id,
            profile=self._build_profile(student_id, records),
            trend=self._build_trend(records),
            weak_points=self._build_weak_points(records),
        )

    def _build_trend(self, records: list[AnswerRecord]) -> list[MasteryTrendPoint]:
        groups: dict[tuple[str, str], dict] = {}
        for r in records:
            if r.course_id is None or r.answered_at is None:
                continue
            key = (r.course_id, r.answered_at.date().isoformat())
            entry = groups.setdefault(key, {"correct": 0, "graded": 0, "title": r.course_title})
            if r.is_correct is True:
                entry["correct"] += 1
            if r.is_correct is not None:
                entry["graded"] += 1
        return [
            MasteryTrendPoint(
                course_id=course_id,
                course_title=entry["title"],
                period=period,
                accuracy=entry["correct"] / entry["graded"],
            )
            for (course_id, period), entry in sorted(
                groups.items(), key=lambda kv: (kv[0][1], kv[0][0])
            )
            if entry["graded"] > 0
        ]

    def _build_weak_points(self, records: list[AnswerRecord]) -> list[WeakPoint]:
        courses: dict[str, dict] = {}
        order: list[str] = []
        for r in records:
            if r.course_id is None:
                continue
            if r.course_id not in courses:
                courses[r.course_id] = {"correct": 0, "graded": 0, "title": r.course_title}
                order.append(r.course_id)
            entry = courses[r.course_id]
            if r.is_correct is True:
                entry["correct"] += 1
            if r.is_correct is not None:
                entry["graded"] += 1

        weak: list[tuple[str, str | None, float]] = []
        for cid in order:
            entry = courses[cid]
            if entry["graded"] == 0:
                continue
            accuracy = entry["correct"] / entry["graded"]
            if accuracy < WEAK_ACCURACY_THRESHOLD:
                weak.append((cid, entry["title"], accuracy))

        weak.sort(key=lambda item: (item[2], item[0]))
        return [
            WeakPoint(
                course_id=cid,
                course_title=title,
                accuracy=accuracy,
                reason=self._reason_for(title, accuracy),
            )
            for cid, title, accuracy in weak[:MAX_WEAK_POINTS]
        ]

    def _reason_for(self, course_title: str | None, accuracy: float) -> str:
        fallback = f"课程「{course_title}」正确率 {accuracy:.0%}，建议回看对应视频并加强练习。"
        try:
            result = self._llm.chat(
                [
                    {"role": "system", "content": WEAK_POINT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"课程「{course_title}」正确率 {accuracy:.0%}，请一句话归因。",
                    },
                ]
            )
            content = (result.content or "").strip()
        except Exception:
            return fallback
        return content or fallback

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
