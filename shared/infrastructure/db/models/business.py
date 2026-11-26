from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, JSON, Numeric, String, Text
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
    __table_args__ = (
        Index("ix_practice_question_video_type", "video_id", "question_type"),
    )

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
    order_index: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ConversationMessage(Base):
    __tablename__ = "conversation_message"
    __table_args__ = (
        Index("ix_conversation_message_conv", "conversation_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    message_id: Mapped[str] = mapped_column(String(64), unique=True)
    conversation_id: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    sources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)
