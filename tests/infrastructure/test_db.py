from sqlalchemy import create_engine

from shared.infrastructure.db.base import Base
import shared.infrastructure.db.models  # noqa: F401  触发模型注册


EXPECTED_TABLES = {
    "course_category",
    "course",
    "chapter",
    "video",
    "video_annotation",
    "student",
    "teacher",
    "student_teacher_relation",
    "student_course",
    "student_video_progress",
    "lead",
    "practice_session",
    "practice_question",
    "practice_answer",
    "learning_profile",
    "mastery_trend",
    "weak_point",
    "conversation_message",
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
