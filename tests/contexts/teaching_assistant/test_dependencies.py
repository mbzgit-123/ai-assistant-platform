from unittest.mock import patch

from contexts.teaching_assistant.interface import dependencies as deps


def test_get_retrieval_is_lazy_singleton():
    deps._retrieval = None
    calls = []

    class _FakeKB:
        def __init__(self, uri, embedding, retrieval_mode, top_k):
            calls.append((uri, embedding, retrieval_mode, top_k))

    with patch.object(deps, "MilvusKnowledgeBase", _FakeKB), patch.object(
        deps, "create_embeddings", lambda model: "emb"
    ):
        a = deps._get_retrieval()
        b = deps._get_retrieval()

    assert a is b
    assert len(calls) == 1
    assert calls[0][1] == "emb"  # 嵌入模型传入检索器
    assert calls[0][3] == 5      # 默认 top_k
