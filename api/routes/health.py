from fastapi import APIRouter

from shared.infrastructure.observability.tracing import get_trace_id
from shared.infrastructure.web.response import ok

router = APIRouter()


@router.get("/health")
async def health():
    return ok(data={"status": "ok"}, trace_id=get_trace_id())


@router.get("/ready")
async def ready():
    return ok(data={"status": "ready"}, trace_id=get_trace_id())
