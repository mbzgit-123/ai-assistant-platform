from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import Course
from api.main import create_app
from contexts.sales_assistant.interface.dependencies import get_sales_chat_service
from shared.infrastructure.db.session import get_session
from shared.infrastructure.llm.fake import FakeLLMAdapter
from shared.infrastructure.memory.in_memory import InMemoryStore
from contexts.sales_assistant.application.service import SalesChatService
from contexts.sales_assistant.infrastructure.repository import SalesRepository
from contexts.sales_assistant.infrastructure.vip_report import StubVipReport


def _client(responses=None, seed=None):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = Session(engine)
    if seed:
        seed(s)
        s.commit()

    def override_session():
        yield s

    def override_service():
        return SalesChatService(
            FakeLLMAdapter(responses=responses),
            InMemoryStore(),
            SalesRepository(s),
            StubVipReport(),
        )

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_sales_chat_service] = override_service
    return TestClient(app)


def test_sales_chat_endpoint_ok():
    def seed(s):
        s.add(Course(course_id="c1", name="AI算法课", price=100, duration_hours=20, highlights="h", direction="AI", position="大模型算法岗"))

    c = _client(
        responses=['{"intent": "course_intro", "direction": "AI", "position": "大模型算法岗"}', "推荐话术"],
        seed=seed,
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
