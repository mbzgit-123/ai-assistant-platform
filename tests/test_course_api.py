from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from api.main import create_app
from contexts.course_assistant.application.service import CourseAssistantService, SupervisionService
from contexts.course_assistant.infrastructure.message_channel import StubMessageChannel
from contexts.course_assistant.infrastructure.path_knowledge import InMemoryPathKnowledge
from contexts.course_assistant.interface.dependencies import (
    get_course_assistant_service,
    get_supervision_service,
)
from shared.infrastructure.db.session import get_session
from shared.infrastructure.llm.fake import FakeLLMAdapter


class _StubProgress:
    def __init__(self):
        self.profile = None
        self.titles = {"ai_py_basic": "Python 基础", "llm_foundation": "大模型基础", "llm_app_dev": "大模型应用"}
        self.completed = set()
        self.enrolled = ["s1"]
        self.last_completed = {}

    def get_profile(self, student_id):
        return self.profile

    def get_course_title(self, course_id):
        return self.titles.get(course_id)

    def completed_course_ids(self, student_id):
        return self.completed

    def enrolled_student_ids(self):
        return self.enrolled

    def last_completed_at(self, student_id):
        return self.last_completed.get(student_id)


def _client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = Session(engine)

    def override_session():
        yield s

    def override_course_service():
        return CourseAssistantService(FakeLLMAdapter(responses=["学习内容"]), InMemoryPathKnowledge(), _StubProgress())

    def override_supervision_service():
        return SupervisionService(_StubProgress(), StubMessageChannel())

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_course_assistant_service] = override_course_service
    app.dependency_overrides[get_supervision_service] = override_supervision_service
    return TestClient(app)


def test_course_plan_endpoint_ok():
    c = _client()
    r = c.post("/api/v1/course/plan", json={"position": "大模型应用开发岗", "studentId": "s1"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["position"] == "大模型应用开发岗"
    assert body["data"]["items"][0]["courseId"]


def test_course_plan_validation_error():
    c = _client()
    r = c.post("/api/v1/course/plan", json={})
    assert r.status_code == 400
    assert r.json()["code"] == 40000


def test_course_refresh_endpoint_ok():
    c = _client()
    r = c.post("/api/v1/course/plan/refresh", json={"position": "大模型应用开发岗", "studentId": "s1"})
    assert r.status_code == 200
    assert r.json()["code"] == 0


def test_supervision_check_endpoint_ok():
    c = _client()
    r = c.post("/api/v1/course/supervision/check")
    assert r.status_code == 200
    assert r.json()["code"] == 0
    assert isinstance(r.json()["data"], list)
