from fastapi import Depends
from sqlalchemy.orm import Session

from contexts.learning_analytics.application.service import LearningAnalyticsService
from contexts.learning_analytics.infrastructure.repository import LearningRepository
from shared.infrastructure.config import get_settings
from shared.infrastructure.db.session import get_session
from shared.infrastructure.llm.factory import get_llm


def get_learning_analytics_service(
    session: Session = Depends(get_session),
) -> LearningAnalyticsService:
    return LearningAnalyticsService(
        data=LearningRepository(session),
        llm=get_llm(get_settings()),
    )
