import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from api.main import create_app
from contexts.teaching_assistant.application.service import TeachingAssistantService
from contexts.teaching_assistant.domain.chunks import RetrievedChunk
from contexts.teaching_assistant.infrastructure.conversation_repository import ConversationRepository
from contexts.teaching_assistant.interface.dependencies import get_teaching_assistant_service
from shared.infrastructure.db.session import get_session
from shared.infrastructure.llm.fake import FakeLLMAdapter


class _StubRetrieval:
    """固定返回一条高分命中，保证分数可控（不依赖真实 Milvus）。"""

    def search(self, question, top_k):
        return [
            RetrievedChunk(
                chunk_id="chunk_a",
                document_name="课程.md",
                chapter="第2章",
                heading_path="第2章 > 2.1",
                text="循环结构 用于 重复 执行 代码",
                score=0.8,
            )
        ]


def _client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = Session(engine)

    def override_session():
        yield s

    def override_service():
        return TeachingAssistantService(
            FakeLLMAdapter(responses=["循环结构讲解"]),
            _StubRetrieval(),
            ConversationRepository(s),
        )

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_teaching_assistant_service] = override_service
    return TestClient(app)


def test_teaching_ask_endpoint_ok():
    c = _client()
    r = c.post("/api/v1/teaching/ask", json={"question": "什么是循环结构"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["reply"] == "循环结构讲解"
    assert body["data"]["sources"][0]["chapterId"] == "第2章"
    assert body["data"]["conversationId"].startswith("conv_")


def test_teaching_ask_endpoint_passes_conversation_id():
    c = _client()
    r = c.post("/api/v1/teaching/ask", json={"question": "什么是循环结构", "conversationId": "conv_abc"})
    assert r.status_code == 200
    assert r.json()["data"]["conversationId"] == "conv_abc"


def test_teaching_ask_endpoint_validation_error():
    c = _client()
    r = c.post("/api/v1/teaching/ask", json={})
    assert r.status_code == 400
    assert r.json()["code"] == 40000


def test_teaching_ask_endpoint_empty_question_rejected():
    c = _client()
    r = c.post("/api/v1/teaching/ask", json={"question": ""})
    assert r.status_code == 400
    assert r.json()["code"] == 40000


def test_teaching_ask_stream_endpoint():
    c = _client()
    r = c.post("/api/v1/teaching/ask/stream", json={"question": "什么是循环结构", "studentId": "s_1"})
    assert r.status_code == 200
    events = [json.loads(line[6:]) for line in r.text.split("\n") if line.startswith("data: ")]
    assert events[0]["type"] == "meta"
    assert events[0]["conversationId"].startswith("conv_")
    assert events[0]["sources"][0]["chapterId"] == "第2章"
    deltas = [e["content"] for e in events if e["type"] == "delta"]
    assert "".join(deltas) == "循环结构讲解"
    assert events[-1]["type"] == "done"


def test_teaching_conversations_endpoint():
    c = _client()
    c.post("/api/v1/teaching/ask", json={"question": "什么是循环结构", "studentId": "s_1"})
    r = c.get("/api/v1/teaching/conversations", params={"userId": "s_1"})
    assert r.status_code == 200
    convs = r.json()["data"]
    assert len(convs) == 1
    assert convs[0]["title"] == "什么是循环结构"
    assert convs[0]["messageCount"] == 2


def test_teaching_messages_endpoint():
    c = _client()
    resp = c.post("/api/v1/teaching/ask", json={"question": "什么是循环结构", "studentId": "s_1"})
    conv_id = resp.json()["data"]["conversationId"]
    r = c.get(f"/api/v1/teaching/conversations/{conv_id}")
    assert r.status_code == 200
    msgs = r.json()["data"]
    assert len(msgs) == 2
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "什么是循环结构"
    assert msgs[1]["content"] == "循环结构讲解"
    assert msgs[1]["sources"][0]["chapterId"] == "第2章"
