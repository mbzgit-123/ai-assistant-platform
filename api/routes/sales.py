from fastapi import APIRouter, Depends

from api.dependencies import get_sales_chat_service
from api.schemas import ok
from api.schemas.sales import SalesChatRequest
from contexts.sales_assistant.application.service import SalesChatService
from shared.infrastructure.observability.tracing import get_trace_id

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
