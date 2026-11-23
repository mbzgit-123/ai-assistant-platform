import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from contexts.sales_assistant.application.service import SalesChatService
from contexts.sales_assistant.interface.dependencies import get_sales_chat_service
from contexts.sales_assistant.interface.schemas import SalesChatRequest
from shared.infrastructure.observability.tracing import get_trace_id
from shared.infrastructure.web.response import ok

router = APIRouter(prefix="/api/v1/sales", tags=["sales"])


@router.post("/chat")
async def chat(
    body: SalesChatRequest,
    service: SalesChatService = Depends(get_sales_chat_service),
):
    return ok(
        data=service.chat(body.conversationId, body.message, body.source),
        trace_id=get_trace_id(),
    )


@router.post("/chat/stream")
async def chat_stream(
    body: SalesChatRequest,
    service: SalesChatService = Depends(get_sales_chat_service),
):
    def event_stream():
        for event in service.chat_stream(body.conversationId, body.message, body.source):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
