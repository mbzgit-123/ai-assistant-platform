from dataclasses import dataclass
from typing import Protocol


@dataclass
class Question:
    question_id: str
    video_id: str
    question_type: str  # multi_choice | short_answer | scenario | code_fill
    content: dict
    reference_answer: dict
    explanation: str


@dataclass
class GradeResult:
    is_correct: bool
    score: float
    feedback: str


class QuestionGenerationPort(Protocol):
    def plan_counts(self, video_ids: list[str]) -> dict[str, int]: ...

    def generate_by_video(self, video_id: str, count: int) -> list[Question]: ...

    def generate_from_document(self, course_document: str) -> list[Question]: ...


class GradingPort(Protocol):
    def grade(self, question: Question, answer_content: dict) -> GradeResult: ...
