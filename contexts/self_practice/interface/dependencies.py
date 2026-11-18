from fastapi import Depends
from sqlalchemy.orm import Session

from contexts.exam_grading.infrastructure.adapter import GradingAdapter
from contexts.exam_paper_generation.infrastructure.adapter import QuestionGenerationAdapter
from contexts.self_practice.application.service import PracticeService
from contexts.self_practice.infrastructure.repository import PracticeRepository
from shared.infrastructure.config import get_settings
from shared.infrastructure.db.session import get_session
from shared.infrastructure.llm.factory import get_llm


def get_practice_service(session: Session = Depends(get_session)) -> PracticeService:
    llm = get_llm(get_settings())
    return PracticeService(
        QuestionGenerationAdapter(session, llm),
        GradingAdapter(session, llm),
        PracticeRepository(session),
    )
