from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.db.base import Base, utcnow


class Lead(Base):
    __tablename__ = "lead"

    lead_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    student_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact: Mapped[str] = mapped_column(String(64))
    direction: Mapped[str] = mapped_column(String(64))
    position: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)
    vip_reported: Mapped[bool | None] = mapped_column(Boolean, default=False)


class PracticeSession(Base):
    __tablename__ = "practice_session"

    practice_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    student_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    video_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_score: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)


class PracticeQuestion(Base):
    __tablename__ = "practice_question"

    question_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    practice_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    question_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reference_answer: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)


class PracticeAnswer(Base):
    __tablename__ = "practice_answer"

    answer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    practice_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    question_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    student_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    answer_content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)


class LearningProfile(Base):
    __tablename__ = "learning_profile"

    student_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)


class MasteryTrend(Base):
    __tablename__ = "mastery_trend"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mastery_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    stat_date: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)


class WeakPoint(Base):
    __tablename__ = "weak_point"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    point: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)


class ConversationMessage(Base):
    __tablename__ = "conversation_message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    student_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)
