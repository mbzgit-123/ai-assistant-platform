from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from contexts.learning_analytics.infrastructure.repository import LearningRepository
from shared.infrastructure.db.base import Base, utcnow
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.business import (
    PracticeAnswer,
    PracticeQuestion,
    PracticeSession,
)
from shared.infrastructure.db.models.sync_cache import (
    Chapter,
    Course,
    StudentCourse,
    StudentVideoProgress,
    Video,
)


def _session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def test_enrolled_course_count():
    s = _session()
    s.add_all(
        [
            StudentCourse(id=1, student_id="s1", course_id="c1"),
            StudentCourse(id=2, student_id="s1", course_id="c2"),
            StudentCourse(id=3, student_id="s2", course_id="c1"),
        ]
    )
    s.commit()
    assert LearningRepository(s).enrolled_course_count("s1") == 2


def test_completed_video_count():
    s = _session()
    s.add_all(
        [
            StudentVideoProgress(id=1, student_id="s1", video_id="v1", completed_at=utcnow()),
            StudentVideoProgress(id=2, student_id="s1", video_id="v2", completed_at=None),
        ]
    )
    s.commit()
    assert LearningRepository(s).completed_video_count("s1") == 1


def test_enrolled_video_count():
    s = _session()
    s.add_all(
        [
            Course(course_id="c1", name="Python 基础"),
            Chapter(chapter_id="ch1", course_id="c1", title="循环"),
            Chapter(chapter_id="ch2", course_id="c1", title="函数"),
            Video(video_id="v1", chapter_id="ch1", title="视频1"),
            Video(video_id="v2", chapter_id="ch2", title="视频2"),
            StudentCourse(id=1, student_id="s1", course_id="c1"),
        ]
    )
    s.commit()
    assert LearningRepository(s).enrolled_video_count("s1") == 2


def test_answer_records_join_session_and_get_course():
    s = _session()
    t = utcnow()
    s.add_all(
        [
            PracticeSession(
                practice_id="p1", student_id="s1", course_id="c1", course_title="循环结构"
            ),
            PracticeQuestion(
                question_id="q1", practice_id="p1", video_id="v1", question_type="choice"
            ),
            PracticeAnswer(
                answer_id="a1",
                practice_id="p1",
                question_id="q1",
                student_id="s1",
                is_correct=True,
                score=1.0,
                answered_at=t,
            ),
        ]
    )
    s.commit()
    records = LearningRepository(s).answer_records("s1")
    assert len(records) == 1
    r = records[0]
    assert r.question_type == "choice"
    assert r.video_id == "v1"
    assert r.course_id == "c1"
    assert r.course_title == "循环结构"
    assert r.is_correct is True
    assert r.score == 1.0
    assert r.answered_at == t


def test_answer_records_filters_by_student():
    s = _session()
    s.add_all(
        [
            PracticeSession(practice_id="p1", student_id="s1", course_id="c1"),
            PracticeQuestion(question_id="q1", practice_id="p1", video_id="v1"),
            PracticeAnswer(
                answer_id="a1", practice_id="p1", question_id="q1", student_id="s1"
            ),
            PracticeAnswer(
                answer_id="a2", practice_id="p1", question_id="q1", student_id="s2"
            ),
        ]
    )
    s.commit()
    assert len(LearningRepository(s).answer_records("s1")) == 1


def test_last_completed_at_returns_latest():
    s = _session()
    now = utcnow()
    later = now - timedelta(days=1)
    s.add_all(
        [
            StudentVideoProgress(
                id=1, student_id="s1", video_id="v1", completed_at=now - timedelta(days=5)
            ),
            StudentVideoProgress(id=2, student_id="s1", video_id="v2", completed_at=later),
        ]
    )
    s.commit()
    last = LearningRepository(s).last_completed_at("s1")
    assert last is not None
    assert abs((last - later).total_seconds()) < 1


def test_last_completed_at_none_when_no_progress():
    assert LearningRepository(_session()).last_completed_at("s1") is None
