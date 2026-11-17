from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.db.base import Base, utcnow


class CourseCategory(Base):
    __tablename__ = "course_category"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    name: Mapped[str] = mapped_column(String(128))
    path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)


class Course(Base):
    __tablename__ = "course"

    course_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    name: Mapped[str] = mapped_column(String(256))
    price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    duration_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    highlights: Mapped[str | None] = mapped_column(Text, nullable=True)
    direction: Mapped[str | None] = mapped_column(String(64), nullable=True)
    position: Mapped[str | None] = mapped_column(String(64), nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)


class Chapter(Base):
    __tablename__ = "chapter"

    chapter_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    course_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(256))
    content_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)


class Video(Base):
    __tablename__ = "video"

    video_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chapter_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(256))
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mp4_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)


class VideoAnnotation(Base):
    __tablename__ = "video_annotation"

    video_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chapter_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    start_sentence: Mapped[str | None] = mapped_column(Text, nullable=True)
    end_sentence: Mapped[str | None] = mapped_column(Text, nullable=True)
    fallback_range: Mapped[str | None] = mapped_column(String(64), nullable=True)
    annotated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    annotated_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)


class Student(Base):
    __tablename__ = "student"

    student_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    education: Mapped[str | None] = mapped_column(String(32), nullable=True)
    major: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vip_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)


class Teacher(Base):
    __tablename__ = "teacher"

    teacher_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)


class StudentTeacherRelation(Base):
    __tablename__ = "student_teacher_relation"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    teacher_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class StudentCourse(Base):
    __tablename__ = "student_course"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    course_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    purchased_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)


class StudentVideoProgress(Base):
    __tablename__ = "student_video_progress"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chapter_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)
