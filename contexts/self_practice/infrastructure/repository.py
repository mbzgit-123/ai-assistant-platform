import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from contexts.self_practice.domain.ports import GradeResult, Question
from shared.infrastructure.db.base import utcnow
from shared.infrastructure.db.models.business import (
    PracticeAnswer,
    PracticeQuestion,
    PracticeSession,
)
from shared.infrastructure.db.models.sync_cache import StudentVideoProgress, Video


class PracticeRepository:
    def __init__(self, session: Session):
        self._session = session

    def list_completed_videos(self, student_id: str, chapter_id: str) -> list[dict]:
        stmt = (
            select(Video)
            .join(StudentVideoProgress, StudentVideoProgress.video_id == Video.video_id)
            .where(
                StudentVideoProgress.student_id == student_id,
                StudentVideoProgress.completed_at.isnot(None),
                Video.chapter_id == chapter_id,
            )
        )
        videos = self._session.scalars(stmt).all()
        return [
            {"videoId": v.video_id, "title": v.title, "durationSeconds": v.duration_seconds}
            for v in videos
        ]

    def get_video_durations(self, video_ids: list[str]) -> dict[str, int]:
        if not video_ids:
            return {}
        stmt = select(Video).where(Video.video_id.in_(video_ids))
        videos = self._session.scalars(stmt).all()
        return {v.video_id: v.duration_seconds for v in videos if v.duration_seconds is not None}

    def find_questions_by_video(self, video_id: str) -> list[Question]:
        stmt = select(PracticeQuestion).where(
            PracticeQuestion.video_id == video_id,
            PracticeQuestion.status == "active",
        )
        rows = self._session.scalars(stmt).all()
        return [self._to_question(r) for r in rows]

    def save_session(self, practice_id: str, student_id: str, video_ids: list[str]) -> None:
        self._session.add(
            PracticeSession(
                practice_id=practice_id,
                student_id=student_id,
                video_ids=video_ids,
                status="in_progress",
            )
        )
        self._session.commit()

    def save_questions(self, practice_id: str, questions: list[Question]) -> None:
        for q in questions:
            self._session.add(
                PracticeQuestion(
                    question_id=q.question_id,
                    practice_id=practice_id,
                    video_id=q.video_id,
                    question_type=q.question_type,
                    content=q.content,
                    reference_answer=q.reference_answer,
                    explanation=q.explanation,
                    status="active",
                )
            )
        self._session.commit()

    def save_answers(
        self,
        practice_id: str,
        student_id: str | None,
        answers: list[tuple[Question, dict, GradeResult]],
    ) -> None:
        for idx, (question, answer_content, grade) in enumerate(answers):
            self._session.add(
                PracticeAnswer(
                    answer_id="a_" + uuid.uuid4().hex[:12],
                    practice_id=practice_id,
                    question_id=question.question_id,
                    student_id=student_id,
                    answer_content=answer_content,
                    is_correct=grade.is_correct,
                    score=grade.score,
                    feedback=grade.feedback,
                    order_index=idx,
                )
            )
        self._session.commit()

    def get_question(self, question_id: str) -> Question | None:
        row = self._session.get(PracticeQuestion, question_id)
        if row is None:
            return None
        return self._to_question(row)

    def get_session_student_id(self, practice_id: str) -> str | None:
        session = self._session.get(PracticeSession, practice_id)
        return session.student_id if session else None

    def mark_session_submitted(self, practice_id: str, total_score: float) -> None:
        session = self._session.get(PracticeSession, practice_id)
        if session is None:
            return
        session.status = "submitted"
        session.submitted_at = utcnow()
        session.total_score = total_score
        self._session.commit()

    def list_sessions(self, student_id: str) -> list[dict]:
        stmt = (
            select(PracticeSession)
            .where(PracticeSession.student_id == student_id)
            .order_by(PracticeSession.started_at.desc())
        )
        sessions = self._session.scalars(stmt).all()
        return [
            {
                "practiceId": s.practice_id,
                "startedAt": s.started_at,
                "status": s.status,
                "correctCount": self._count_correct(s.practice_id),
                "questionCount": self._count_questions(s.practice_id),
            }
            for s in sessions
        ]

    def _count_correct(self, practice_id: str) -> int:
        stmt = select(PracticeAnswer).where(
            PracticeAnswer.practice_id == practice_id,
            PracticeAnswer.is_correct.is_(True),
        )
        return len(self._session.scalars(stmt).all())

    def _count_questions(self, practice_id: str) -> int:
        stmt = select(PracticeAnswer).where(PracticeAnswer.practice_id == practice_id)
        return len(self._session.scalars(stmt).all())

    def get_practice_result(self, practice_id: str) -> dict | None:
        session = self._session.get(PracticeSession, practice_id)
        if session is None:
            return None
        stmt = (
            select(PracticeAnswer)
            .where(PracticeAnswer.practice_id == practice_id)
            .order_by(PracticeAnswer.order_index.asc())
        )
        answers = self._session.scalars(stmt).all()
        results = []
        total = len(answers)
        correct = 0
        score = 0.0
        for a in answers:
            question = self._session.get(PracticeQuestion, a.question_id)
            if a.is_correct:
                correct += 1
            score += float(a.score or 0.0)
            results.append(
                {
                    "questionId": a.question_id,
                    "questionType": question.question_type if question else None,
                    "content": question.content if question else None,
                    "answerContent": a.answer_content,
                    "isCorrect": bool(a.is_correct),
                    "score": float(a.score or 0.0),
                    "referenceAnswer": question.reference_answer if question else None,
                    "explanation": question.explanation if question else None,
                    "feedback": a.feedback,
                }
            )
        return {
            "practiceId": practice_id,
            "submittedAt": session.submitted_at,
            "summary": {"total": total, "correct": correct, "score": score},
            "results": results,
        }

    def _to_question(self, row: PracticeQuestion) -> Question:
        return Question(
            question_id=row.question_id,
            video_id=row.video_id or "",
            question_type=row.question_type or "",
            content=row.content or {},
            reference_answer=row.reference_answer or {},
            explanation=row.explanation or "",
        )
