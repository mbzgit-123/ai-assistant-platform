from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import Video
from api.main import create_app
from api.dependencies import get_practice_service
from shared.infrastructure.db.session import get_session
from shared.infrastructure.llm.fake import FakeLLMAdapter
from contexts.exam_paper_generation.infrastructure.adapter import QuestionGenerationAdapter
from contexts.exam_grading.infrastructure.adapter import GradingAdapter
from contexts.self_practice.infrastructure.repository import PracticeRepository
from contexts.self_practice.application.service import PracticeService


def _client(seed=None):
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
        llm = FakeLLMAdapter()
        return PracticeService(
            QuestionGenerationAdapter(s, llm), GradingAdapter(s, llm), PracticeRepository(s))

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_practice_service] = override_service
    return TestClient(app)


def test_available_videos_endpoint():
    c = _client()
    r = c.get("/api/v1/practice/available-videos?studentId=stu&chapterId=c1")
    assert r.status_code == 200
    assert r.json()["code"] == 0


def test_start_endpoint_admission_blocked():
    c = _client()
    r = c.post("/api/v1/practice/start", json={"studentId": "stu", "chapterId": "c1", "videoIds": []})
    assert r.status_code == 400  # 空视频累计时长 0 < 60 分钟


def test_start_and_submit_roundtrip():
    def seed(s):
        s.add(Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600))

    c = _client(seed=seed)
    start = c.post("/api/v1/practice/start",
                   json={"studentId": "stu", "chapterId": "c1", "videoIds": ["v1"]})
    assert start.status_code == 200
    data = start.json()["data"]
    pid = data["practiceId"]
    assert pid.startswith("pr_") and data["groupedByVideo"] is True
    answers = [{"questionId": q["questionId"], "answerContent": {"selected": "A"}}
               for q in data["questions"]]
    sub = c.post("/api/v1/practice/submit", json={"practiceId": pid, "answers": answers})
    assert sub.status_code == 200
    body = sub.json()["data"]
    assert body["summary"]["total"] == len(data["questions"])
