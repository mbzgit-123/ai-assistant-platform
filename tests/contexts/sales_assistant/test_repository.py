from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401
from shared.infrastructure.db.models.sync_cache import Course
from shared.infrastructure.db.models.business import Lead
from contexts.sales_assistant.infrastructure.repository import SalesRepository


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def test_find_courses_by_direction():
    s = _session()
    s.add(Course(course_id="c1", name="Java入门", price=100, duration_hours=20, highlights="h", direction="Java", position=None))
    s.add(Course(course_id="c2", name="AI算法", price=200, duration_hours=30, highlights="h", direction="AI", position="大模型算法岗"))
    s.commit()
    rows = SalesRepository(s).find_courses("Java")
    assert len(rows) == 1
    assert rows[0]["courseId"] == "c1"
    assert rows[0]["price"] == 100.0


def test_find_courses_by_direction_and_position():
    s = _session()
    s.add(Course(course_id="c2", name="AI算法", price=200, duration_hours=30, highlights="h", direction="AI", position="大模型算法岗"))
    s.add(Course(course_id="c3", name="AI应用", price=300, duration_hours=40, highlights="h", direction="AI", position="大模型应用开发岗"))
    s.commit()
    rows = SalesRepository(s).find_courses("AI", "大模型算法岗")
    assert len(rows) == 1
    assert rows[0]["courseId"] == "c2"


def test_find_courses_no_match_returns_empty():
    s = _session()
    assert SalesRepository(s).find_courses("前端") == []


def test_save_lead_persists():
    s = _session()
    lead = SalesRepository(s).save_lead("13800138000", "AI", "大模型算法岗", "备注", "web")
    assert lead.lead_id.startswith("lead_")
    assert lead.direction == "AI"
    fetched = s.get(Lead, lead.lead_id)
    assert fetched is not None
    assert fetched.contact == "13800138000"
