import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from api.main import create_app
from contexts.sales_assistant.interface.dependencies import get_sales_chat_service
from shared.infrastructure.db.session import get_session
from shared.infrastructure.llm.fake import FakeLLMAdapter
from shared.infrastructure.memory.in_memory import InMemoryStore
from contexts.sales_assistant.application.service import SalesChatService
from contexts.sales_assistant.domain.catalog import CourseInfo, SubjectNode
from contexts.sales_assistant.infrastructure.repository import SalesRepository
from contexts.sales_assistant.infrastructure.vip_report import StubVipReport


class FakeKnowledgeBase:
    def search(self, question, top_k=4):
        return []


class FakeCourseCatalog:
    def __init__(self, courses=()):
        self._courses = list(courses)
        self._tree = [
            SubjectNode(
                id="ai_id",
                name="人工智能",
                parent_id=None,
                children=(
                    SubjectNode(id="algo_id", name="大模型算法开发岗", parent_id="ai_id"),
                ),
            )
        ]

    def get_subject_tree(self):
        return self._tree

    def get_courses(self, subject_id, subject_parent_id):
        return list(self._courses)


def _client(responses=None, catalog=None):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = Session(engine)

    def override_session():
        yield s

    def override_service():
        return SalesChatService(
            FakeLLMAdapter(responses=responses),
            InMemoryStore(),
            SalesRepository(s),
            StubVipReport(),
            FakeKnowledgeBase(),
            catalog=catalog,
        )

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_sales_chat_service] = override_service
    return TestClient(app)


def test_sales_chat_endpoint_ok():
    catalog = FakeCourseCatalog(
        courses=[
            CourseInfo(
                id="c1", title="AI算法课", description="d", price=100.0,
                lesson_num=18, duration=9902.0, cover="",
            )
        ]
    )
    c = _client(
        responses=['{"intent": "course_intro", "direction": "人工智能", "position": "大模型算法开发岗"}', "推荐话术"],
        catalog=catalog,
    )
    r = c.post("/api/v1/sales/chat", json={"message": "想学AI", "source": "web"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["conversationId"].startswith("c_")
    assert body["data"]["courses"][0]["courseId"] == "c1"


def test_sales_chat_endpoint_validation_error():
    c = _client()
    r = c.post("/api/v1/sales/chat", json={})
    assert r.status_code == 400
    assert r.json()["code"] == 40000


def test_sales_chat_cors_preflight():
    c = _client()
    r = c.options(
        "/api/v1/sales/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "*"


def test_sales_chat_stream_endpoint():
    c = _client(responses=['{"intent": "direction_guide", "direction": "", "position": ""}'])
    r = c.post("/api/v1/sales/chat/stream", json={"message": "你好", "source": "web"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    data_lines = [ln for ln in r.text.split("\n") if ln.startswith("data: ")]
    events = [json.loads(ln[len("data: "):]) for ln in data_lines]
    assert [e["type"] for e in events] == ["meta", "delta", "done"]
    assert events[0]["conversationId"].startswith("c_")
    assert "人工智能" in events[1]["content"]
