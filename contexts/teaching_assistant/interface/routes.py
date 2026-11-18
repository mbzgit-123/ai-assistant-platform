from fastapi import APIRouter, Depends

from contexts.teaching_assistant.application.service import TeachingAssistantService
from contexts.teaching_assistant.interface.dependencies import get_teaching_assistant_service
from contexts.teaching_assistant.interface.schemas import AskRequest
from shared.infrastructure.observability.tracing import get_trace_id
from shared.infrastructure.web.response import ok

router = APIRouter(prefix="/api/v1/teaching", tags=["teaching"])


@router.post("/ask")
async def ask(
    body: AskRequest,
    service: TeachingAssistantService = Depends(get_teaching_assistant_service),
):
    return ok(
        data=service.ask(body.question, body.studentId),
        trace_id=get_trace_id(),
    )
