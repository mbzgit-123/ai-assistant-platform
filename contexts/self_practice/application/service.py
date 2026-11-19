import random
import uuid

from contexts.self_practice.domain.admission import check_admission
from contexts.self_practice.domain.merge import merge_counts
from contexts.self_practice.domain.ports import (
    GradeResult,
    GradingPort,
    Question,
    QuestionGenerationPort,
)
from contexts.self_practice.infrastructure.repository import PracticeRepository
from shared.common.exception.base import BadRequestError
from shared.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class PracticeService:
    def __init__(
        self,
        qgen: QuestionGenerationPort,
        grader: GradingPort,
        repo: PracticeRepository,
    ):
        self._qgen = qgen
        self._grader = grader
        self._repo = repo

    def available_videos(self, student_id: str, chapter_id: str) -> list[dict]:
        return self._repo.list_completed_videos(student_id, chapter_id)

    def start_practice(
        self,
        student_id: str,
        chapter_id: str,
        video_ids: list[str],
        confirm: bool = False,
        regenerate: bool = False,
    ) -> dict:
        durations = self._repo.get_video_durations(video_ids)
        admission = check_admission(sum(durations.values()))
        if admission.level == "block":
            raise BadRequestError("累计时长不足 30 分钟")
        if admission.level == "over":
            raise BadRequestError("累计时长超过 90 分钟上限")
        if admission.level == "soft" and not confirm:
            raise BadRequestError("累计时长在 30–60 分钟，请确认后开始")

        practice_id = "pr_" + uuid.uuid4().hex[:12]

        reused_questions: list[Question] = []
        new_videos: list[str] = []
        for vid in video_ids:
            if not regenerate:
                existing = self._repo.find_questions_by_video(vid)
                if existing:
                    random.shuffle(existing)
                    reused_questions.extend(existing)
                    continue
            new_videos.append(vid)

        new_questions: list[Question] = []
        if new_videos:
            plan = self._qgen.plan_counts(new_videos)
            counts = [plan.get(vid, 0) for vid in new_videos]
            merged = merge_counts(counts)
            for vid, cnt in zip(new_videos, merged):
                new_questions.extend(self._qgen.generate_by_video(vid, cnt))

        questions = reused_questions + new_questions

        self._repo.save_session(practice_id, student_id, video_ids)
        self._repo.save_questions(practice_id, new_questions)

        return {
            "practiceId": practice_id,
            "groupedByVideo": True,
            "questions": [self._to_public_question(q) for q in questions],
        }

    def submit_practice(self, practice_id: str, answers: list[dict]) -> dict:
        graded: list[tuple[Question, dict, GradeResult]] = []
        for answer in answers:
            question_id = answer.get("questionId")
            question = self._repo.get_question(question_id)
            if question is None:
                logger.warning(
                    "question_not_found", practice_id=practice_id, question_id=question_id
                )
                continue
            answer_content = answer.get("answerContent", {})
            grade = self._grader.grade(question, answer_content)
            graded.append((question, answer_content, grade))

        student_id = self._repo.get_session_student_id(practice_id)
        self._repo.save_answers(practice_id, student_id, graded)

        total = len(graded)
        correct = sum(1 for _, _, g in graded if g.is_correct)
        score = sum(g.score for _, _, g in graded)
        self._repo.mark_session_submitted(practice_id, score)
        results = [
            {
                "questionId": q.question_id,
                "isCorrect": g.is_correct,
                "score": g.score,
                "referenceAnswer": q.reference_answer,
                "explanation": q.explanation,
                "feedback": g.feedback,
            }
            for q, _, g in graded
        ]
        return {
            "practiceId": practice_id,
            "summary": {"total": total, "correct": correct, "score": score},
            "results": results,
        }

    def get_practice(self, practice_id: str) -> dict | None:
        return self._repo.get_practice_result(practice_id)

    def get_history(self, student_id: str) -> dict:
        return {"sessions": self._repo.list_sessions(student_id)}

    def _to_public_question(self, q: Question) -> dict:
        return {
            "questionId": q.question_id,
            "videoId": q.video_id,
            "questionType": q.question_type,
            "content": q.content,
        }
