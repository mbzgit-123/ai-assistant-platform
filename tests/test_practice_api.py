import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import Chapter, Video, VideoAnnotation
from api.main import create_app
from contexts.self_practice.interface.dependencies import get_practice_service
from shared.infrastructure.db.session import get_session
from shared.infrastructure.llm.fake import FakeLLMAdapter
from contexts.exam_paper_generation.infrastructure.adapter import QuestionGenerationAdapter
from contexts.exam_grading.infrastructure.adapter import GradingAdapter
from contexts.self_practice.infrastructure.repository import PracticeRepository
from contexts.self_practice.application.service import PracticeService


def _client(seed=None, gen_responses=None, grade_responses=None):
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
        gen_llm = FakeLLMAdapter(responses=gen_responses)
        grade_llm = FakeLLMAdapter(responses=grade_responses)
        return PracticeService(
            QuestionGenerationAdapter(s, gen_llm),
            GradingAdapter(s, grade_llm),
            PracticeRepository(s),
        )

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_practice_service] = override_service
    return TestClient(app)


def test_available_videos_endpoint():
    c = _client()
    r = c.get("/api/v1/practice/available-videos?studentId=stu&chapterId=c1")
    assert r.status_code == 200
    assert r.json()["code"] == 0


def test_history_endpoint_empty():
    c = _client()
    r = c.get("/api/v1/practice/history?studentId=stu")
    assert r.status_code == 200
    assert r.json()["code"] == 0
    assert r.json()["data"]["sessions"] == []


def test_start_endpoint_admission_blocked():
    c = _client()
    r = c.post("/api/v1/practice/start", json={"studentId": "stu", "chapterId": "c1", "videoIds": []})
    assert r.status_code == 400  # 空视频累计时长 0 < 60 分钟


def test_start_and_submit_roundtrip():
    def seed(s):
        s.add(Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600))
        s.add(VideoAnnotation(video_id="v1", chapter_id="c1", start_sentence="S", end_sentence="E"))
        s.add(Chapter(chapter_id="c1", title="ch", content_md="S 知识点内容 E"))

    multi_choice_items = [
        {"content": {"stem": "选择题", "options": ["A", "B", "C", "D"]},
         "reference_answer": {"correct": ["A"]}, "explanation": "解析"}
        for _ in range(4)
    ]
    short_items = [
        {"content": {"stem": "简答题"}, "reference_answer": {"points": ["要点"]}, "explanation": "解析"}
        for _ in range(3)
    ]
    scenario_items = [
        {"content": {"scenario": "场景", "task": "任务"},
         "reference_answer": {"points": ["要点"]}, "explanation": "解析"}
        for _ in range(3)
    ]
    gen_responses = [
        json.dumps(multi_choice_items, ensure_ascii=False),
        json.dumps(short_items, ensure_ascii=False),
        json.dumps(scenario_items, ensure_ascii=False),
    ]
    grade_responses = [json.dumps({"is_correct": True, "score": 0.8, "feedback": "ok"})]

    c = _client(seed=seed, gen_responses=gen_responses, grade_responses=grade_responses)
    start = c.post("/api/v1/practice/start",
                   json={"studentId": "stu", "chapterId": "c1", "videoIds": ["v1"]})
    assert start.status_code == 200
    data = start.json()["data"]
    pid = data["practiceId"]
    assert pid.startswith("pr_") and data["groupedByVideo"] is True
    assert len(data["questions"]) == 10  # multi_choice 4 + short_answer 3 + scenario 3
    answers = [{"questionId": q["questionId"], "answerContent": {"selected": ["A"]}}
               for q in data["questions"]]
    sub = c.post("/api/v1/practice/submit", json={"practiceId": pid, "answers": answers})
    assert sub.status_code == 200
    body = sub.json()["data"]
    assert body["summary"]["total"] == 10


def test_chapter_exam_endpoint():
    multi_choice_items = [
        {"content": {"stem": f"选择题{i}", "options": ["A", "B", "C", "D"]},
         "reference_answer": {"correct": ["A"]}, "explanation": "解析"}
        for i in range(20)
    ]
    short_items = [
        {"content": {"stem": f"简答题{i}"}, "reference_answer": {"points": ["要点"]}, "explanation": "解析"}
        for i in range(5)
    ]
    scenario_items = [
        {"content": {"scenario": "场景", "task": "任务"},
         "reference_answer": {"points": ["要点"]}, "explanation": "解析"}
        for _ in range(1)
    ]
    gen_responses = [
        json.dumps(multi_choice_items, ensure_ascii=False),
        json.dumps(short_items, ensure_ascii=False),
        json.dumps(scenario_items, ensure_ascii=False),
    ]

    c = _client(gen_responses=gen_responses)
    r = c.post("/api/v1/practice/chapter-exam", json={
        "studentId": "stu",
        "chapterId": "c1",
        "videos": [
            {"videoId": "v1", "title": "视频一", "summary": "要点A"},
            {"videoId": "v2", "title": "视频二", "summary": "要点B"},
        ],
    })
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["practiceId"].startswith("pr_")
    types = [q["type"] for q in data["questions"]]
    assert types.count("indefinite") == 20
    assert types.count("essay") == 5
    assert types.count("scenario") == 1
    assert types.count("code") == 0  # 无代码块，代码填空静默跳过
