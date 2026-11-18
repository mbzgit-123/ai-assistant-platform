from contexts.teaching_assistant.application.service import TeachingAssistantService, HANDOFF_REPLY
from contexts.teaching_assistant.domain.chunks import Chunk
from contexts.teaching_assistant.infrastructure.handoff import StubHandoff
from contexts.teaching_assistant.infrastructure.vector_store import InMemoryVectorStore
from shared.infrastructure.llm.fake import FakeLLMAdapter


class _StubEmbedding:
    """按文本是否含关键词返回同向/正交向量，保证分数可控（不依赖真实 embedding 质量）。"""
    def embed(self, text: str) -> list[float]:
        if "循环" in text or "什么是" in text:
            return [1.0, 0.0]
        return [0.0, 1.0]


def _chunk(chunk_id, text, heading="2.1"):
    return Chunk(chunk_id=chunk_id, chapter_id="c1", course_id="course1",
                 text=text, heading_path="第2章 > " + heading, source_ref=heading)


def _service(llm_responses=None, chunks=None):
    embedding = _StubEmbedding()
    store = InMemoryVectorStore(embedding)
    if chunks:
        store.upsert(chunks)
    llm = FakeLLMAdapter(responses=llm_responses or ["讲解内容"])
    return TeachingAssistantService(llm, embedding, store, StubHandoff())


def test_ask_handoff_on_keyword():
    svc = _service()
    r = svc.ask("我要转人工", "s_1")
    assert r["handoff"] is True
    assert r["reply"] == HANDOFF_REPLY
    assert r["sources"] == []


def test_ask_handoff_on_empty_question():
    svc = _service()
    r = svc.ask("   ", None)
    assert r["handoff"] is True


def test_ask_handoff_on_empty_store():
    svc = _service()
    r = svc.ask("什么是循环结构", None)
    assert r["handoff"] is True


def test_ask_returns_llm_reply_and_sources():
    svc = _service(
        llm_responses=["循环结构用于重复执行一段代码。"],
        chunks=[_chunk("chunk_a", "循环结构 用于 重复 执行 一段 代码")],
    )
    r = svc.ask("什么是循环结构", None)
    assert r["handoff"] is False
    assert r["reply"] == "循环结构用于重复执行一段代码。"
    assert r["sources"][0]["chapterId"] == "c1"
    assert r["sources"][0]["headingPath"] == "第2章 > 2.1"
    assert r["sources"][0]["sourceRef"] == "2.1"


def test_ask_excludes_low_score_chunks_from_sources():
    # 命中块（含「循环」→ score 1.0）与无关块（→ score 0.0 < 阈值）并存
    svc = _service(
        llm_responses=["讲解"],
        chunks=[
            _chunk("chunk_hit", "循环 结构 重复 执行", heading="2.1"),
            _chunk("chunk_irrelevant", "完全无关 的 内容 主题 别的 领域 词汇", heading="2.9"),
        ],
    )
    r = svc.ask("什么是循环结构", None)
    assert r["handoff"] is False
    source_refs = [s["sourceRef"] for s in r["sources"]]
    assert "2.1" in source_refs           # 命中块进入 sources
    assert "2.9" not in source_refs       # 无关块（score 0.0）被排除
