from contexts.teaching_assistant.application.service import (
    TeachingAssistantService,
    UNABLE_TO_ANSWER_REPLY,
)
from contexts.teaching_assistant.domain.chunks import RetrievedChunk
from shared.infrastructure.llm.fake import FakeLLMAdapter


class _StubRetrieval:
    """按预设命中列表返回检索结果，分数可控（不依赖真实 Milvus）。"""

    def __init__(self, hits):
        self._hits = hits
        self.queries = []

    def search(self, question, top_k):
        self.queries.append((question, top_k))
        return self._hits


class _RecordingRecord:
    def __init__(self):
        self.exchanges = []
        self.conversations = []
        self.messages = []

    def record_exchange(self, conversation_id, user_id, question, reply, sources):
        self.exchanges.append(
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "question": question,
                "reply": reply,
                "sources": sources,
            }
        )

    def list_conversations(self, user_id):
        return self.conversations

    def list_messages(self, conversation_id):
        return self.messages


def _hit(chunk_id, text, score, chapter="第2章 控制流程", heading="第2章 控制流程 > 2.1 变量"):
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_name="课程.md",
        chapter=chapter,
        heading_path=heading,
        text=text,
        score=score,
    )


def _service(llm_responses=None, hits=None, record=None):
    retrieval = _StubRetrieval(hits or [])
    llm = FakeLLMAdapter(responses=llm_responses or ["讲解内容"])
    record = record or _RecordingRecord()
    return TeachingAssistantService(llm, retrieval, record), record, retrieval


def test_ask_returns_reply_sources_and_conversation_id():
    svc, _, _ = _service(
        llm_responses=["循环结构用于重复执行一段代码。"],
        hits=[_hit("chunk_a", "循环结构 用于 重复 执行 一段 代码", score=0.8)],
    )
    r = svc.ask("什么是循环结构", "s_1")
    assert r["reply"] == "循环结构用于重复执行一段代码。"
    assert r["sources"][0]["chapterId"] == "第2章 控制流程"
    assert r["sources"][0]["headingPath"] == "课程.md > 第2章 控制流程 > 2.1 变量"
    assert r["sources"][0]["sourceRef"] == "2.1 变量"
    assert r["conversationId"].startswith("conv_")


def test_ask_returns_unable_to_answer_on_low_confidence():
    svc, _, _ = _service(hits=[])  # 空检索 → 低置信度
    r = svc.ask("什么是循环结构", None)
    assert r["reply"] == UNABLE_TO_ANSWER_REPLY
    assert r["sources"] == []
    assert r["conversationId"].startswith("conv_")


def test_ask_reuses_provided_conversation_id():
    svc, _, _ = _service(
        llm_responses=["讲解"],
        hits=[_hit("chunk_a", "循环 结构 重复 执行", score=0.8)],
    )
    r = svc.ask("什么是循环结构", "s_1", conversation_id="conv_abc")
    assert r["conversationId"] == "conv_abc"


def test_ask_records_exchange():
    svc, rec, _ = _service(
        llm_responses=["循环结构用于重复执行一段代码。"],
        hits=[_hit("chunk_a", "循环结构 用于 重复 执行 一段 代码", score=0.8)],
    )
    svc.ask("什么是循环结构", "s_1", conversation_id="conv_abc")
    assert len(rec.exchanges) == 1
    ex = rec.exchanges[0]
    assert ex["conversation_id"] == "conv_abc"
    assert ex["user_id"] == "s_1"
    assert ex["question"] == "什么是循环结构"
    assert ex["reply"] == "循环结构用于重复执行一段代码。"
    assert ex["sources"][0]["chapterId"] == "第2章 控制流程"


def test_ask_records_unable_to_answer_exchange():
    svc, rec, _ = _service(hits=[])
    svc.ask("什么是循环结构", "s_1")
    assert len(rec.exchanges) == 1
    ex = rec.exchanges[0]
    assert ex["reply"] == UNABLE_TO_ANSWER_REPLY
    assert ex["sources"] == []


def test_ask_does_not_raise_on_record_failure():
    class _FailingRecord:
        def record_exchange(self, *args, **kwargs):
            raise RuntimeError("db down")

    svc, _, _ = _service(
        llm_responses=["讲解"],
        hits=[_hit("chunk_a", "循环 结构 重复 执行", score=0.8)],
        record=_FailingRecord(),
    )
    r = svc.ask("什么是循环结构", "s_1")
    assert r["reply"] == "讲解"  # 落库失败不影响主流程


def test_ask_excludes_low_score_chunks_from_sources():
    svc, _, _ = _service(
        llm_responses=["讲解"],
        hits=[
            _hit("chunk_hit", "循环 结构 重复 执行", score=0.8, heading="第2章 控制流程 > 2.1 变量"),
            _hit("chunk_low", "完全无关 的 内容", score=0.3, heading="第2章 控制流程 > 2.9 其他"),
        ],
    )
    r = svc.ask("什么是循环结构", None)
    source_refs = [s["sourceRef"] for s in r["sources"]]
    assert "2.1 变量" in source_refs       # 命中块进入 sources
    assert "2.9 其他" not in source_refs   # 低分块被排除


def test_ask_dedupes_sources_from_same_section():
    svc, _, _ = _service(
        llm_responses=["讲解"],
        hits=[
            _hit("chunk_1", "激活函数 tanh 定义", score=0.8, heading="第3章 神经网络 > 激活函数 > 理解非线性因素"),
            _hit("chunk_2", "tanh 导数与梯度消失", score=0.75, heading="第3章 神经网络 > 激活函数 > 理解非线性因素"),
        ],
    )
    r = svc.ask("Tanh 激活函数是什么", "s_1")
    assert [s["sourceRef"] for s in r["sources"]] == ["理解非线性因素"]


def test_ask_stream_yields_meta_delta_done():
    svc, rec, _ = _service(
        llm_responses=["循环结构"],
        hits=[_hit("chunk_a", "循环 结构 重复 执行", score=0.8)],
    )
    events = list(svc.ask_stream("什么是循环结构", "s_1", conversation_id="conv_abc"))
    assert events[0]["type"] == "meta"
    assert events[0]["conversationId"] == "conv_abc"
    assert events[0]["sources"][0]["chapterId"] == "第2章 控制流程"
    deltas = [e["content"] for e in events if e["type"] == "delta"]
    assert "".join(deltas) == "循环结构"
    assert events[-1] == {"type": "done"}
    assert len(rec.exchanges) == 1
    assert rec.exchanges[0]["reply"] == "循环结构"


def test_ask_stream_unable_to_answer():
    svc, rec, _ = _service(hits=[])
    events = list(svc.ask_stream("什么是循环结构", "s_1"))
    assert events[0]["type"] == "meta"
    assert events[0]["sources"] == []
    assert events[1] == {"type": "delta", "content": UNABLE_TO_ANSWER_REPLY}
    assert events[-1] == {"type": "done"}
    assert rec.exchanges[0]["reply"] == UNABLE_TO_ANSWER_REPLY
    assert rec.exchanges[0]["sources"] == []


def test_ask_stream_reuses_conversation_id():
    svc, _, _ = _service(
        llm_responses=["讲解"],
        hits=[_hit("chunk_a", "循环 结构 重复 执行", score=0.8)],
    )
    events = list(svc.ask_stream("什么是循环结构", "s_1", conversation_id="conv_abc"))
    assert events[0]["conversationId"] == "conv_abc"


def test_ask_searches_with_top_k():
    svc, _, retrieval = _service(hits=[])
    svc.ask("什么是循环结构", None)
    assert retrieval.queries == [("什么是循环结构", 5)]


def test_list_conversations_delegates():
    svc, rec, _ = _service()
    rec.conversations = [{"conversationId": "conv_1"}]
    assert svc.list_conversations("s_1") == [{"conversationId": "conv_1"}]


def test_list_messages_delegates():
    svc, rec, _ = _service()
    rec.messages = [{"role": "user", "content": "q"}]
    assert svc.list_messages("conv_1") == [{"role": "user", "content": "q"}]
