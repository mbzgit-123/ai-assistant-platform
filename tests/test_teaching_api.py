from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import Chapter
from api.main import create_app
from contexts.teaching_assistant.application.service import TeachingAssistantService
from contexts.teaching_assistant.domain.chunks import Chunk
from contexts.teaching_assistant.infrastructure.handoff import StubHandoff
from contexts.teaching_assistant.infrastructure.vector_store import InMemoryVectorStore
from contexts.teaching_assistant.interface.dependencies import get_teaching_assistant_service
from shared.infrastructure.db.session import get_session
from shared.infrastructure.llm.fake import FakeLLMAdapter


class _StubEmbedding:
    """按文本是否含关键词返回同向/正交向量，保证分数可控（不依赖真实 embedding 质量）。"""

    def embed(self, text: str) -> list[float]:
        if "循环" in text or "什么是" in text:
            return [1.0, 0.0]
        return [0.0, 1.0]


def _client(seed=None):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = Session(engine)
    if seed:
        seed(s)
        s.commit()

    def override_session():
        yield s

    def override_service():
        embedding = _StubEmbedding()
        store = InMemoryVectorStore(embedding)
        store.upsert([Chunk(chunk_id="chunk_a", chapter_id="c1", course_id="course1",
                            text="循环结构 用于 重复 执行 代码",
                            heading_path="第2章 > 2.1", source_ref="2.1")])
        return TeachingAssistantService(FakeLLMAdapter(responses=["循环结构讲解"]),
                                        embedding, store, StubHandoff())

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
    assert body["data"]["handoff"] is False
    assert body["data"]["reply"] == "循环结构讲解"
    assert body["data"]["sources"][0]["chapterId"] == "c1"


def test_teaching_ask_endpoint_validation_error():
    c = _client()
    r = c.post("/api/v1/teaching/ask", json={})
    assert r.status_code == 400
    assert r.json()["code"] == 40000
