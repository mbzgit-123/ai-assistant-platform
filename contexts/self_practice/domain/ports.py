from dataclasses import dataclass
from typing import Protocol


@dataclass
class Question:
    question_id: str
    video_id: str
    question_type: str  # choice | short_answer | scenario | code
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


class GradingPort(Protocol):
    def grade(self, question: Question, answer_content: dict) -> GradeResult: ...
