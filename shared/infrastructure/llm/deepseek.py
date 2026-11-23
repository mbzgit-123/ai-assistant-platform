from shared.infrastructure.llm.port import LLMResult


class DeepSeekAdapter:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int,
        max_retries: int,
    ):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = None

    def _get_client(self):
        if self._client is None:
            from langchain_openai import ChatOpenAI

            self._client = ChatOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                model=self._model,
                timeout=self._timeout,
                max_retries=self._max_retries,
            )
        return self._client

    def chat(self, messages: list[dict[str, str]]) -> LLMResult:
        resp = self._get_client().invoke(messages)
        usage = getattr(resp, "usage_metadata", None) or {}
        prompt_tokens = usage.get("input_tokens", 0) if isinstance(usage, dict) else 0
        completion_tokens = usage.get("output_tokens", 0) if isinstance(usage, dict) else 0
        return LLMResult(
            content=resp.content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def stream(self, messages: list[dict[str, str]]):
        for chunk in self._get_client().stream(messages):
            content = chunk.content
            if content:
                yield content
