from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import Video, StudentVideoProgress
from shared.common.exception.base import BadRequestError
from contexts.self_practice.domain.ports import Question, GradeResult
from contexts.self_practice.infrastructure.repository import PracticeRepository
from contexts.self_practice.application.service import PracticeService


class FakeQGen:
    def __init__(self):
        self.calls = 0

    def plan_counts(self, video_ids):
        return {vid: 10 for vid in video_ids}

    def generate_by_video(self, video_id, count):
        self.calls += 1
        return [
            Question(f"q_{video_id}_{i}", video_id, "choice",
                     {"stem": "s", "options": ["A", "B", "C", "D"]},
                     {"correct": "A"}, "exp")
            for i in range(count)
        ]


class FakeGrader:
    def grade(self, question, answer_content):
        return GradeResult(True, 1.0, "正确")


def _service(videos=None, completed=None):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = Session(engine)
    if videos:
        s.add_all(videos)
        s.commit()
    if completed:
        s.add_all(completed)
        s.commit()
    return PracticeService(FakeQGen(), FakeGrader(), PracticeRepository(s))


def test_start_admission_blocked():
    svc = _service(videos=[Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=600)])
    with pytest.raises(BadRequestError):
        svc.start_practice("stu", "c1", ["v1"])


def test_start_generates_and_persists():
    svc = _service(videos=[
        Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600),
    ])
    result = svc.start_practice("stu", "c1", ["v1"])
    assert result["practiceId"].startswith("pr_")
    assert result["groupedByVideo"] is True
    assert len(result["questions"]) == 10


def test_start_reuses_without_regenerating():
    qgen = FakeQGen()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = Session(engine)
    s.add(Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600))
    s.commit()
    repo = PracticeRepository(s)
    # 预置已有题目（复用）
    repo.save_questions("pr_old", [Question("q_existing", "v1", "choice",
        {"stem": "s", "options": ["A", "B", "C", "D"]}, {"correct": "A"}, "exp")])
    svc = PracticeService(qgen, FakeGrader(), repo)
    result = svc.start_practice("stu", "c1", ["v1"])
    assert qgen.calls == 0  # 未调用生成
    assert [q["questionId"] for q in result["questions"]] == ["q_existing"]


def test_available_videos_only_completed():
    svc = _service(
        videos=[Video(video_id="v1", chapter_id="c1", title="t1", duration_seconds=600),
                Video(video_id="v2", chapter_id="c1", title="t2", duration_seconds=600)],
        completed=[StudentVideoProgress(id=1, student_id="stu", video_id="v1", chapter_id="c1",
                                        completed_at=datetime(2026, 11, 17))],
    )
    vids = svc.available_videos("stu", "c1")
    assert [v["videoId"] for v in vids] == ["v1"]


def test_submit_grades_and_returns_summary():
    svc = _service(videos=[Video(video_id="v1", chapter_id="c1", title="t", duration_seconds=3600)])
    start = svc.start_practice("stu", "c1", ["v1"])
    pid = start["practiceId"]
    answers = [{"questionId": q["questionId"], "answerContent": {"selected": "A"}}
               for q in start["questions"]]
    result = svc.submit_practice(pid, answers)
    assert result["summary"]["total"] == 10
    assert result["summary"]["correct"] == 10
    assert len(result["results"]) == 10
