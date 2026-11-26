"""真实集成测试：BGE-M3 嵌入 + Milvus Lite 建库 + 语义检索（dense / hybrid）。

依赖重（torch / langchain-milvus / langchain-huggingface），仅在 myenv 环境运行；
缺少依赖时自动跳过（pytest.importorskip）。
"""

import pytest

pytest.importorskip("torch")
pytest.importorskip("langchain_milvus")
pytest.importorskip("langchain_huggingface")

from contexts.teaching_assistant.infrastructure.knowledge_base import (
    CHUNKS_FILE,
    MilvusKnowledgeBase,
    build_knowledge_base,
)
from shared.infrastructure.embeddings import create_embeddings


def test_real_chunks_build_and_retrieve(tmp_path):
    embeddings = create_embeddings()
    uri = str(tmp_path / "milvus_teaching.db")

    count = build_knowledge_base(chunks_file=CHUNKS_FILE, uri=uri, embedding=embeddings)
    assert count > 0

    dense = MilvusKnowledgeBase(uri=uri, embedding=embeddings, retrieval_mode="dense")
    hits = dense.search("什么是反向传播", top_k=3)
    assert hits
    assert any("反向传播" in (h.chapter + h.heading_path + h.text) for h in hits)

    hybrid = MilvusKnowledgeBase(uri=uri, embedding=embeddings, retrieval_mode="hybrid")
    hybrid_hits = hybrid.search("张量怎么广播", top_k=3)
    assert hybrid_hits
    assert any("广播" in (h.chapter + h.heading_path + h.text) for h in hybrid_hits)
