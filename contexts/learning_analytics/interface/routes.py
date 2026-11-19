from fastapi import APIRouter, Depends

from contexts.learning_analytics.application.service import LearningAnalyticsService
from contexts.learning_analytics.interface.dependencies import (
    get_learning_analytics_service,
)
from shared.infrastructure.observability.tracing import get_trace_id
from shared.infrastructure.web.response import ok

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/student/{studentId}")
async def student_analysis(
    studentId: str,
    service: LearningAnalyticsService = Depends(get_learning_analytics_service),
):
    return ok(data=service.analyze(studentId).to_dict(), trace_id=get_trace_id())
