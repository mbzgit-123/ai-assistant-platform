from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class AnswerRecord:
    question_type: str | None = None
    video_id: str | None = None
    course_id: str | None = None
    course_title: str | None = None
    is_correct: bool | None = None
    score: float | None = None
    answered_at: datetime | None = None


class LearningDataPort(Protocol):
    def enrolled_course_count(self, student_id: str) -> int: ...

    def completed_video_count(self, student_id: str) -> int: ...

    def enrolled_video_count(self, student_id: str) -> int: ...

    def answer_records(self, student_id: str) -> list[AnswerRecord]: ...

    def last_completed_at(self, student_id: str) -> datetime | None: ...
