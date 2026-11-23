from shared.infrastructure.config import Settings
from shared.infrastructure.llm.deepseek import DeepSeekAdapter
from shared.infrastructure.llm.fake import FakeLLMAdapter
from shared.infrastructure.llm.factory import get_llm


def test_fake_returns_responses_in_order():
    llm = FakeLLMAdapter(responses=["a", "b"])
    assert llm.chat([{"role": "user", "content": "hi"}]).content == "a"
    assert llm.chat([{"role": "user", "content": "hi"}]).content == "b"
    assert llm.chat([{"role": "user", "content": "hi"}]).content == "b"


def test_fake_stream_yields_content_in_chunks():
    llm = FakeLLMAdapter(responses=["abc"])
    assert list(llm.stream([{"role": "user", "content": "hi"}])) == ["a", "b", "c"]


class _Chunk:
    def __init__(self, content):
        self.content = content


class _FakeStreamClient:
    def stream(self, messages):
        yield _Chunk("a")
        yield _Chunk("")
        yield _Chunk("b")


def test_deepseek_stream_yields_chunk_contents():
    adapter = DeepSeekAdapter("x", "http://x", "m", 1, 1)
    adapter._client = _FakeStreamClient()
    assert list(adapter.stream([{"role": "user", "content": "hi"}])) == ["a", "b"]


def test_factory_fake():
    llm = get_llm(Settings(_env_file=None, llm_provider="fake"))
    assert isinstance(llm, FakeLLMAdapter)


def test_factory_deepseek():
    llm = get_llm(Settings(_env_file=None, llm_provider="deepseek", deepseek_api_key="sk-x"))
    assert isinstance(llm, DeepSeekAdapter)
    assert llm._model == "deepseek-chat"
