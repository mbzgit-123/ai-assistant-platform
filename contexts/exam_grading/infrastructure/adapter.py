import json

from sqlalchemy.orm import Session

from contexts.exam_grading.domain.grading import grade_choice
from contexts.self_practice.domain.ports import GradeResult, Question
from shared.infrastructure.llm.port import LLMPort
from shared.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class GradingAdapter:
    def __init__(self, session: Session, llm: LLMPort):
        self._session = session
        self._llm = llm

    def grade(self, question: Question, answer_content: dict) -> GradeResult:
        if question.question_type == "choice":
            correct, score = grade_choice(answer_content, question.reference_answer)
            return GradeResult(correct, score, "正确" if correct else "错误")
        return self._grade_subjective(question, answer_content)

    def _grade_subjective(self, question: Question, answer_content: dict) -> GradeResult:
        prompt = self._build_prompt(question, answer_content)
        for _ in range(2):  # 初次 + 重试一次
            result = self._llm.chat(prompt)
            try:
                data = json.loads(result.content)
            except (ValueError, TypeError):
                continue
            if isinstance(data, dict):
                return GradeResult(
                    is_correct=bool(data.get("is_correct", False)),
                    score=float(data.get("score", 0.0)),
                    feedback=str(data.get("feedback", "")),
                )
        logger.warning("grading_failed", question_id=question.question_id)
        return GradeResult(False, 0.0, "转人工批改")

    def _build_prompt(self, question: Question, answer_content: dict) -> list[dict[str, str]]:
        payload = json.dumps(
            {"reference_answer": question.reference_answer, "answer": answer_content},
            ensure_ascii=False,
        )
        return [
            {"role": "system", "content": "你是批改 Agent，输出 JSON。"},
            {"role": "user", "content": payload},
        ]
