from typing import Protocol

from contexts.course_assistant.domain.path import PathStep


class PathKnowledgePort(Protocol):
    def get_path(self, position: str) -> list[PathStep]: ...
