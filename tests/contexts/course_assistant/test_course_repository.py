from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base, utcnow
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import (
    Chapter,
    Course,
    Student,
    StudentCourse,
    StudentVideoProgress,
)
from contexts.course_assistant.infrastructure.repository import CourseRepository


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_get_profile_returns_education_and_major():
    s = _session()
    s.add(Student(student_id="s1", education="本科", major="计算机"))
    s.commit()
    p = CourseRepository(s).get_profile("s1")
    assert p.education == "本科"
    assert p.major == "计算机"


def test_get_profile_missing_returns_none():
    assert CourseRepository(_session()).get_profile("nope") is None


def test_completed_course_ids_joins_via_chapter():
    s = _session()
    s.add_all([
        Chapter(chapter_id="ch1", course_id="course_a", title="章节1"),
        Chapter(chapter_id="ch2", course_id="course_b", title="章节2"),
        StudentVideoProgress(id=1, student_id="s1", chapter_id="ch1", completed_at=utcnow()),
        StudentVideoProgress(id=2, student_id="s1", chapter_id="ch2", completed_at=None),
    ])
    s.commit()
    assert CourseRepository(s).completed_course_ids("s1") == {"course_a"}


def test_enrolled_student_ids_distinct():
    s = _session()
    s.add_all([
        StudentCourse(id=1, student_id="s1", course_id="c1"),
        StudentCourse(id=2, student_id="s2", course_id="c2"),
    ])
    s.commit()
    assert CourseRepository(s).enrolled_student_ids() == ["s1", "s2"]


def test_last_completed_at_returns_latest():
    s = _session()
    now = utcnow()
    later = now - timedelta(days=1)
    s.add_all([
        StudentVideoProgress(id=1, student_id="s1", chapter_id="ch1", completed_at=now - timedelta(days=5)),
        StudentVideoProgress(id=2, student_id="s1", chapter_id="ch2", completed_at=later),
    ])
    s.commit()
    last = CourseRepository(s).last_completed_at("s1")
    assert last is not None
    assert abs((last - later).total_seconds()) < 1


def test_get_course_title():
    s = _session()
    s.add(Course(course_id="c1", name="Python 基础"))
    s.commit()
    assert CourseRepository(s).get_course_title("c1") == "Python 基础"
