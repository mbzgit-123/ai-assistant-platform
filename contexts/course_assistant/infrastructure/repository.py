from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from contexts.course_assistant.domain.ports import StudentProfile
from shared.infrastructure.db.models.sync_cache import (
    Chapter,
    Course,
    Student,
    StudentCourse,
    StudentVideoProgress,
)


class CourseRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_profile(self, student_id: str) -> StudentProfile | None:
        student = self._session.get(Student, student_id)
        if student is None:
            return None
        return StudentProfile(education=student.education, major=student.major)

    def completed_course_ids(self, student_id: str) -> set[str]:
        stmt = (
            select(Chapter.course_id)
            .join(StudentVideoProgress, StudentVideoProgress.chapter_id == Chapter.chapter_id)
            .where(
                StudentVideoProgress.student_id == student_id,
                StudentVideoProgress.completed_at.isnot(None),
            )
            .distinct()
        )
        return {c for c in self._session.execute(stmt).scalars().all() if c is not None}

    def enrolled_student_ids(self) -> list[str]:
        stmt = (
            select(StudentCourse.student_id)
            .where(StudentCourse.student_id.isnot(None))
            .distinct()
        )
        return [s for s in self._session.execute(stmt).scalars().all() if s is not None]

    def last_completed_at(self, student_id: str) -> datetime | None:
        stmt = select(func.max(StudentVideoProgress.completed_at)).where(
            StudentVideoProgress.student_id == student_id
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_course_title(self, course_id: str) -> str | None:
        course = self._session.get(Course, course_id)
        return course.name if course else None
