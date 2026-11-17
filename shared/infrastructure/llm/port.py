from dataclasses import dataclass
from typing import Protocol


@dataclass
class LLMResult:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMPort(Protocol):
    def chat(self, messages: list[dict[str, str]]) -> LLMResult: ...
