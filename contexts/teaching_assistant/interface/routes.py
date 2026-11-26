import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

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
        data=service.ask(body.question, body.studentId, body.conversationId),
        trace_id=get_trace_id(),
    )


@router.post("/ask/stream")
async def ask_stream(
    body: AskRequest,
    service: TeachingAssistantService = Depends(get_teaching_assistant_service),
):
    def event_stream():
        for event in service.ask_stream(body.question, body.studentId, body.conversationId):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/conversations")
async def list_conversations(
    userId: str = Query(...),
    service: TeachingAssistantService = Depends(get_teaching_assistant_service),
):
    return ok(data=service.list_conversations(userId), trace_id=get_trace_id())


@router.get("/conversations/{conversationId}")
async def list_messages(
    conversationId: str,
    service: TeachingAssistantService = Depends(get_teaching_assistant_service),
):
    return ok(data=service.list_messages(conversationId), trace_id=get_trace_id())
