from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from contexts.course_assistant.domain.path import PathStep


@dataclass
class StudentProfile:
    education: str | None
    major: str | None


class PathKnowledgePort(Protocol):
    def get_path(self, position: str) -> list[PathStep]: ...


class ProgressPort(Protocol):
    def get_profile(self, student_id: str) -> StudentProfile | None: ...

    def completed_course_ids(self, student_id: str) -> set[str]: ...

    def enrolled_student_ids(self) -> list[str]: ...

    def last_completed_at(self, student_id: str) -> datetime | None: ...

    def get_course_title(self, course_id: str) -> str | None: ...
