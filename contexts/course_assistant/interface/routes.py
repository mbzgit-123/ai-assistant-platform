from fastapi import APIRouter, Depends

from contexts.course_assistant.application.service import (
    CourseAssistantService,
    SupervisionService,
)
from contexts.course_assistant.interface.dependencies import (
    get_course_assistant_service,
    get_supervision_service,
)
from contexts.course_assistant.interface.schemas import PlanRequest
from shared.infrastructure.observability.tracing import get_trace_id
from shared.infrastructure.web.response import ok

router = APIRouter(prefix="/api/v1/course", tags=["course"])


@router.post("/plan")
async def plan(
    body: PlanRequest,
    service: CourseAssistantService = Depends(get_course_assistant_service),
):
    return ok(
        data=service.generate_plan(body.position, body.studentId).to_dict(),
        trace_id=get_trace_id(),
    )


@router.post("/plan/refresh")
async def refresh_plan(
    body: PlanRequest,
    service: CourseAssistantService = Depends(get_course_assistant_service),
):
    return ok(
        data=service.replan(body.position, body.studentId).to_dict(),
        trace_id=get_trace_id(),
    )


@router.post("/supervision/check")
async def supervision_check(
    service: SupervisionService = Depends(get_supervision_service),
):
    return ok(
        data=service.check_and_notify(),
        trace_id=get_trace_id(),
    )
