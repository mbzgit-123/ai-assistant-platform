from shared.infrastructure.llm.port import LLMResult


class FakeLLMAdapter:
    def __init__(self, responses: list[str] | None = None):
        self._responses = responses if responses else ["ok"]
        self._calls = 0

    def chat(self, messages: list[dict[str, str]]) -> LLMResult:
        idx = min(self._calls, len(self._responses) - 1)
        self._calls += 1
        return LLMResult(content=self._responses[idx])
