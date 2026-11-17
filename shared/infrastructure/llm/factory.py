from shared.infrastructure.config import Settings
from shared.infrastructure.llm.deepseek import DeepSeekAdapter
from shared.infrastructure.llm.fake import FakeLLMAdapter
from shared.infrastructure.llm.port import LLMPort


def get_llm(settings: Settings) -> LLMPort:
    if settings.llm_provider == "deepseek":
        return DeepSeekAdapter(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
    return FakeLLMAdapter()
