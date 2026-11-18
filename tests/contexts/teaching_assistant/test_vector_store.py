from contexts.teaching_assistant.domain.chunks import Chunk
from contexts.teaching_assistant.infrastructure.embedding import HashEmbedding
from contexts.teaching_assistant.infrastructure.vector_store import InMemoryVectorStore


def _chunk(chunk_id, text, heading="2.1"):
    return Chunk(chunk_id=chunk_id, chapter_id="c1", course_id="course1",
                 text=text, heading_path="第2章 > " + heading, source_ref=heading)


def test_search_returns_top_k_by_relevance():
    store = InMemoryVectorStore(HashEmbedding())
    store.upsert([
        _chunk("chunk_a", "循环结构 用于 重复 执行 代码"),
        _chunk("chunk_b", "变量 用于 存储 数据"),
        _chunk("chunk_c", "循环 结构 重复 执行"),
    ])
    results = store.search(HashEmbedding().embed("什么是循环结构"), top_k=2)
    assert len(results) == 2
    assert results[0].chunk.chunk_id == "chunk_a" or results[0].chunk.chunk_id == "chunk_c"
    assert results[0].score >= results[1].score


def test_upsert_dedupes_by_chunk_id():
    store = InMemoryVectorStore(HashEmbedding())
    store.upsert([_chunk("chunk_a", "循环结构 重复 执行")])
    store.upsert([_chunk("chunk_a", "循环结构 重复 执行")])
    results = store.search(HashEmbedding().embed("循环结构"), top_k=10)
    assert len(results) == 1


def test_search_empty_store_returns_empty():
    store = InMemoryVectorStore(HashEmbedding())
    assert store.search(HashEmbedding().embed("任意问题"), top_k=5) == []


def test_search_zero_vector_query_does_not_crash():
    store = InMemoryVectorStore(HashEmbedding())
    store.upsert([_chunk("chunk_a", "循环结构 重复 执行")])
    results = store.search([0.0] * 256, top_k=5)
    assert len(results) == 1
    assert results[0].score == 0.0
