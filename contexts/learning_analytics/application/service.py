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
        groups: dict[tuple[str, str], tuple[int, int]] = {}
        for r in records:
            if r.chapter_id is None or r.answered_at is None:
                continue
            key = (r.chapter_id, r.answered_at.date().isoformat())
            correct, graded = groups.get(key, (0, 0))
            if r.is_correct is True:
                correct += 1
            if r.is_correct is not None:
                graded += 1
            groups[key] = (correct, graded)
        return [
            MasteryTrendPoint(chapter_id=chapter_id, period=period, accuracy=correct / graded)
            for (chapter_id, period), (correct, graded) in sorted(
                groups.items(), key=lambda kv: (kv[0][1], kv[0][0])
            )
            if graded > 0
        ]

    def _build_weak_points(self, records: list[AnswerRecord]) -> list[WeakPoint]:
        chapters: dict[str, dict] = {}
        order: list[str] = []
        for r in records:
            if r.chapter_id is None:
                continue
            if r.chapter_id not in chapters:
                chapters[r.chapter_id] = {"correct": 0, "graded": 0, "title": r.chapter_title}
                order.append(r.chapter_id)
            entry = chapters[r.chapter_id]
            if r.is_correct is True:
                entry["correct"] += 1
            if r.is_correct is not None:
                entry["graded"] += 1

        weak: list[tuple[str, str | None, float]] = []
        for cid in order:
            entry = chapters[cid]
            if entry["graded"] == 0:
                continue
            accuracy = entry["correct"] / entry["graded"]
            if accuracy < WEAK_ACCURACY_THRESHOLD:
                weak.append((cid, entry["title"], accuracy))

        weak.sort(key=lambda item: (item[2], item[0]))
        return [
            WeakPoint(
                chapter_id=cid,
                chapter_title=title,
                accuracy=accuracy,
                reason=self._reason_for(title, accuracy),
            )
            for cid, title, accuracy in weak[:MAX_WEAK_POINTS]
        ]

    def _reason_for(self, chapter_title: str | None, accuracy: float) -> str:
        fallback = f"章节「{chapter_title}」正确率 {accuracy:.0%}，建议回看对应视频并加强练习。"
        try:
            result = self._llm.chat(
                [
                    {"role": "system", "content": WEAK_POINT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"章节「{chapter_title}」正确率 {accuracy:.0%}，请一句话归因。",
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
