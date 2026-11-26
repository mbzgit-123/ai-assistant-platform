from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from contexts.learning_analytics.domain.ports import AnswerRecord
from shared.infrastructure.db.models.business import (
    PracticeAnswer,
    PracticeQuestion,
    PracticeSession,
)
from shared.infrastructure.db.models.sync_cache import (
    Chapter,
    StudentCourse,
    StudentVideoProgress,
    Video,
)


class LearningRepository:
    def __init__(self, session: Session):
        self._session = session

    def enrolled_course_count(self, student_id: str) -> int:
        stmt = select(func.count()).select_from(StudentCourse).where(
            StudentCourse.student_id == student_id
        )
        return self._session.execute(stmt).scalar_one()

    def completed_video_count(self, student_id: str) -> int:
        stmt = select(func.count()).select_from(StudentVideoProgress).where(
            StudentVideoProgress.student_id == student_id,
            StudentVideoProgress.completed_at.isnot(None),
        )
        return self._session.execute(stmt).scalar_one()

    def enrolled_video_count(self, student_id: str) -> int:
        stmt = (
            select(func.count(func.distinct(Video.video_id)))
            .select_from(StudentCourse)
            .join(Chapter, Chapter.course_id == StudentCourse.course_id)
            .join(Video, Video.chapter_id == Chapter.chapter_id)
            .where(StudentCourse.student_id == student_id)
        )
        return self._session.execute(stmt).scalar_one()

    def answer_records(self, student_id: str) -> list[AnswerRecord]:
        stmt = (
            select(
                PracticeQuestion.question_type,
                PracticeQuestion.video_id,
                PracticeSession.course_id,
                PracticeSession.course_title,
                PracticeAnswer.is_correct,
                PracticeAnswer.score,
                PracticeAnswer.answered_at,
            )
            .select_from(PracticeAnswer)
            .join(PracticeQuestion, PracticeQuestion.question_id == PracticeAnswer.question_id)
            .join(PracticeSession, PracticeSession.practice_id == PracticeAnswer.practice_id)
            .where(PracticeAnswer.student_id == student_id)
        )
        rows = self._session.execute(stmt).all()
        return [
            AnswerRecord(
                question_type=r.question_type,
                video_id=r.video_id,
                course_id=r.course_id,
                course_title=r.course_title,
                is_correct=r.is_correct,
                score=float(r.score) if r.score is not None else None,
                answered_at=r.answered_at,
            )
            for r in rows
        ]

    def last_completed_at(self, student_id: str) -> datetime | None:
        stmt = select(func.max(StudentVideoProgress.completed_at)).where(
            StudentVideoProgress.student_id == student_id
        )
        return self._session.execute(stmt).scalar_one_or_none()
