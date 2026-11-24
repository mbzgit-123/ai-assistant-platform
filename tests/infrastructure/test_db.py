from sqlalchemy import create_engine
from sqlalchemy.dialects import mysql

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401  触发模型注册
from shared.infrastructure.db.models.business import PracticeQuestion
from shared.infrastructure.db.models.sync_cache import Chapter


EXPECTED_TABLES = {
    "course",
    "chapter",
    "video",
    "video_annotation",
    "student",
    "student_course",
    "student_video_progress",
    "lead",
    "practice_session",
    "practice_question",
    "practice_answer",
}


def test_all_tables_registered():
    assert EXPECTED_TABLES <= set(Base.metadata.tables.keys())


def test_create_and_insert():
    from sqlalchemy.orm import Session

    from shared.infrastructure.db.models.business import Lead

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Lead(lead_id="l1", contact="13800000000", direction="AI"))
        s.commit()
        assert s.get(Lead, "l1").contact == "13800000000"


def test_chapter_content_md_uses_longtext_variant():
    col = Chapter.__table__.c.content_md
    assert col.type.compile(dialect=mysql.dialect()) == "LONGTEXT"


def test_practice_question_has_video_type_index():
    ix = next(
        ix for ix in PracticeQuestion.__table__.indexes
        if ix.name == "ix_practice_question_video_type"
    )
    assert [c.name for c in ix.columns] == ["video_id", "question_type"]
