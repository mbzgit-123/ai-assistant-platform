from shared.infrastructure.config import Settings
from shared.infrastructure.llm.deepseek import DeepSeekAdapter
from shared.infrastructure.llm.fake import FakeLLMAdapter
from shared.infrastructure.llm.factory import get_llm


def test_fake_returns_responses_in_order():
    llm = FakeLLMAdapter(responses=["a", "b"])
    assert llm.chat([{"role": "user", "content": "hi"}]).content == "a"
    assert llm.chat([{"role": "user", "content": "hi"}]).content == "b"
    assert llm.chat([{"role": "user", "content": "hi"}]).content == "b"


def test_factory_fake():
    llm = get_llm(Settings(_env_file=None, llm_provider="fake"))
    assert isinstance(llm, FakeLLMAdapter)


def test_factory_deepseek():
    llm = get_llm(Settings(_env_file=None, llm_provider="deepseek", deepseek_api_key="sk-x"))
    assert isinstance(llm, DeepSeekAdapter)
    assert llm._model == "deepseek-chat"
