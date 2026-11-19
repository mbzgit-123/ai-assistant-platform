from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from api.main import create_app
from contexts.learning_analytics.application.service import LearningAnalyticsService
from contexts.learning_analytics.domain.ports import AnswerRecord
from contexts.learning_analytics.interface.dependencies import (
    get_learning_analytics_service,
)
from shared.infrastructure.db.session import get_session
from shared.infrastructure.llm.fake import FakeLLMAdapter


class _StubData:
    def enrolled_course_count(self, student_id):
        return 2

    def completed_video_count(self, student_id):
        return 3

    def enrolled_video_count(self, student_id):
        return 10

    def answer_records(self, student_id):
        return [
            AnswerRecord(
                chapter_id="ch1",
                chapter_title="循环",
                is_correct=False,
                answered_at=datetime(2026, 11, 1, 9, 0),
            ),
        ]

    def last_completed_at(self, student_id):
        return datetime(2026, 11, 1, 8, 0)


def _client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    s = Session(engine)

    def override_session():
        yield s

    def override_service():
        return LearningAnalyticsService(_StubData(), FakeLLMAdapter(responses=["归因"]))

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_learning_analytics_service] = override_service
    return TestClient(app)


def test_analytics_student_endpoint_ok():
    c = _client()
    r = c.get("/api/v1/analytics/student/s1")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["profile"]["enrolledCourses"] == 2
    assert data["profile"]["completedVideos"] == 3
    assert data["profile"]["totalVideos"] == 10
    assert data["profile"]["overallAccuracy"] == 0.0
    assert data["trend"][0]["chapterId"] == "ch1"
    assert data["trend"][0]["period"] == "2026-11-01"
    assert data["weakPoints"][0]["chapterId"] == "ch1"
    assert data["weakPoints"][0]["reason"] == "归因"
