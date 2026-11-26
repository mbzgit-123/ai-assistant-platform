import random
import re
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

# 后端内部题型 -> 前端题型
_TYPE_TO_FRONTEND = {
    "multi_choice": "indefinite",
    "short_answer": "essay",
    "code_fill": "code",
    "scenario": "scenario",
}

_OPTION_LABELS = ["A", "B", "C", "D", "E", "F", "G", "H"]


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

    def generate_practice(
        self,
        student_id: str,
        course_document: str,
        videos: list[dict],
        course_id: str = "",
        course_title: str = "",
    ) -> dict:
        """由前端传入文档 + 视频列表出题（无时长校验、无复用）。

        courseDocument 携带完整内容，videos 仅提供 videoId 用于落库归属。
        courseId/courseTitle 用于把整套题归属到课程，支撑学情分析按课程聚合。
        """
        video_ids = [v.get("videoId", "") for v in videos if v.get("videoId")]
        questions = self._qgen.generate_from_document(course_document)
        practice_id = "pr_" + uuid.uuid4().hex[:12]
        self._repo.save_session(
            practice_id,
            student_id,
            video_ids,
            course_id=course_id or None,
            course_title=course_title or None,
        )
        self._repo.save_questions(practice_id, questions)
        return {
            "practiceId": practice_id,
            "questions": [self._to_frontend_question(q) for q in questions],
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

    def grade_practice(self, practice_id: str, answers: list[dict]) -> dict:
        """判分：接收前端自然作答（下标/数组/字符串），转内部 answerContent 后走统一 grader。"""
        graded: list[tuple[Question, dict, GradeResult]] = []
        for answer in answers:
            question_id = answer.get("questionId")
            question = self._repo.get_question(question_id)
            if question is None:
                logger.warning(
                    "question_not_found", practice_id=practice_id, question_id=question_id
                )
                continue
            answer_content = self._to_answer_content(question, answer.get("answer"))
            grade = self._grader.grade(question, answer_content)
            graded.append((question, answer_content, grade))

        student_id = self._repo.get_session_student_id(practice_id)
        self._repo.save_answers(practice_id, student_id, graded)

        score = sum(g.score for _, _, g in graded)
        total = len(graded)
        self._repo.mark_session_submitted(practice_id, score)

        results = [
            {
                "questionId": q.question_id,
                "isCorrect": g.is_correct,
                "score": g.score,
                "feedback": g.feedback,
                "correctAnswer": self._correct_answer_text(q),
                "reference": q.explanation,  # 前端「参考答案」直接展示题干解析文本
            }
            for q, _, g in graded
        ]
        return {
            "practiceId": practice_id,
            "totalScore": score,
            "fullScore": total,
            "results": results,
        }

    def get_practice(self, practice_id: str) -> dict | None:
        raw = self._repo.get_practice_result(practice_id)
        if raw is None:
            return None
        questions = []
        for r in raw["results"]:
            q = Question(
                question_id=r["questionId"],
                video_id="",
                question_type=r["questionType"] or "",
                content=r["content"] or {},
                reference_answer=r["referenceAnswer"] or {},
                explanation=r["explanation"] or "",
            )
            item = self._to_frontend_question(q)
            item["answer"] = self._answer_to_natural(q, r["answerContent"])
            item["isCorrect"] = r["isCorrect"]
            item["score"] = r["score"]
            item["correctAnswer"] = self._correct_answer_text(q)
            item["explanation"] = q.explanation
            item["feedback"] = r["feedback"]
            questions.append(item)
        return {
            "practiceId": raw["practiceId"],
            "submittedAt": raw.get("submittedAt"),
            "summary": raw["summary"],
            "questions": questions,
        }

    def get_history(self, student_id: str) -> dict:
        return {"sessions": self._repo.list_sessions(student_id)}

    def _to_public_question(self, q: Question) -> dict:
        return {
            "questionId": q.question_id,
            "videoId": q.video_id,
            "questionType": q.question_type,
            "content": q.content,
        }

    def _to_frontend_question(self, q: Question) -> dict:
        """把内部 Question 转成前端 exam.vue 可直接渲染的扁平结构。"""
        qtype = _TYPE_TO_FRONTEND.get(q.question_type, q.question_type)
        content = q.content or {}
        item = {
            "id": q.question_id,
            "type": qtype,
            "stem": content.get("stem", ""),
        }
        if qtype == "indefinite":
            raw_options = content.get("options", [])
            item["options"] = [
                {
                    "label": _OPTION_LABELS[i] if i < len(_OPTION_LABELS) else str(i + 1),
                    "text": opt,
                }
                for i, opt in enumerate(raw_options)
            ]
        elif qtype == "code":
            code = content.get("code", "")
            item["code"] = code
            item["blanks"] = len(re.findall(r"___\(\d+\)___", code))
        elif qtype == "scenario":
            item["scenario"] = content.get("scenario", "")
            item["stem"] = content.get("task", "") or item["stem"]
        return item

    def _correct_answer_text(self, question: Question) -> str:
        """客观题给出可展示的正确答案：选择题 -> 选项字母（如 A、C）；代码填空 -> 各空答案。"""
        ref = question.reference_answer or {}
        if question.question_type == "multi_choice":
            correct = ref.get("correct") or []
            return "、".join(sorted(str(x) for x in correct))
        if question.question_type == "code_fill":
            answers = ref.get("answers") or []
            return "、".join(str(x) for x in answers)
        return ""

    def _answer_to_natural(self, question: Question, answer_content) -> object:
        """把内部 answerContent 转回前端自然作答格式（用于回顾展示）：
        选择题 -> 下标数组；代码填空 -> 答案数组；主观题 -> 字符串。"""
        qtype = question.question_type
        if qtype == "multi_choice":
            labels = (answer_content or {}).get("selected") or []
            idx = []
            for lab in labels:
                try:
                    idx.append(_OPTION_LABELS.index(str(lab)))
                except ValueError:
                    idx.append(str(lab))
            return idx
        if qtype == "code_fill":
            return (answer_content or {}).get("answers") or []
        return (answer_content or {}).get("text") or ""

    def _to_answer_content(self, question: Question, answer) -> dict:
        """把前端自然作答转成内部 answerContent：
        不定项下标数组 -> {"selected": [labels]}；代码答案数组 -> {"answers": [...]}；
        主观题字符串 -> {"text": ...}。"""
        qtype = question.question_type
        if qtype == "multi_choice":
            selected = []
            for idx in answer or []:
                if isinstance(idx, int) and 0 <= idx < len(_OPTION_LABELS):
                    selected.append(_OPTION_LABELS[idx])
                else:
                    selected.append(str(idx))
            return {"selected": selected}
        if qtype == "code_fill":
            return {"answers": list(answer) if isinstance(answer, list) else [answer]}
        return {"text": answer if isinstance(answer, str) else ""}
