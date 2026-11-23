"""真实集成测试：BGE-M3 嵌入 + Milvus Lite 建库 + 语义检索（dense / hybrid）。

依赖重（torch / langchain-milvus / sentence-transformers），仅在 myenv 环境运行；
缺少依赖时自动跳过（pytest.importorskip）。
"""

import pytest

pytest.importorskip("torch")
pytest.importorskip("langchain_milvus")
pytest.importorskip("langchain_huggingface")

from contexts.sales_assistant.infrastructure.embeddings import create_embeddings
from contexts.sales_assistant.infrastructure.knowledge_base import (
    DATA_DIR,
    MilvusKnowledgeBase,
    build_knowledge_base,
)


def test_real_faq_build_and_retrieve(tmp_path):
    embeddings = create_embeddings()
    uri = str(tmp_path / "milvus_sales_faq.db")

    build_knowledge_base(data_dir=DATA_DIR, uri=uri, embedding=embeddings)

    dense = MilvusKnowledgeBase(uri=uri, embedding=embeddings, retrieval_mode="dense")
    hits = dense.search("学习周期一般多久", top_k=3)
    assert hits
    assert any("周期" in h.question for h in hits)

    hybrid = MilvusKnowledgeBase(uri=uri, embedding=embeddings, retrieval_mode="hybrid")
    hybrid_hits = hybrid.search("报名流程是怎样的", top_k=3)
    assert hybrid_hits
    assert any("报名" in h.question for h in hybrid_hits)
