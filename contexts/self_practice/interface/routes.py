from fastapi import APIRouter, Depends

from contexts.self_practice.application.service import PracticeService
from contexts.self_practice.interface.dependencies import get_practice_service
from contexts.self_practice.interface.schemas import (
    GeneratePracticeRequest,
    GradePracticeRequest,
    StartChapterExamRequest,
    StartPracticeRequest,
    SubmitPracticeRequest,
)
from shared.infrastructure.observability.tracing import get_trace_id
from shared.infrastructure.web.response import ok

router = APIRouter(prefix="/api/v1/practice", tags=["practice"])


@router.get("/available-videos")
async def available_videos(
    studentId: str,
    chapterId: str,
    service: PracticeService = Depends(get_practice_service),
):
    videos = service.available_videos(studentId, chapterId)
    return ok(data={"videos": videos}, trace_id=get_trace_id())


@router.post("/start")
async def start_practice(
    body: StartPracticeRequest,
    service: PracticeService = Depends(get_practice_service),
):
    result = service.start_practice(body.studentId, body.chapterId, body.videoIds, body.confirm, body.regenerate)
    return ok(data=result, trace_id=get_trace_id())


@router.post("/generate")
async def generate_practice(
    body: GeneratePracticeRequest,
    service: PracticeService = Depends(get_practice_service),
):
    videos = [v.model_dump() for v in body.videos]
    result = service.generate_practice(
        body.studentId,
        body.courseDocument,
        videos,
        course_id=body.courseId,
        course_title=body.courseTitle,
    )
    return ok(data=result, trace_id=get_trace_id())


@router.post("/chapter-exam")
async def start_chapter_exam(
    body: StartChapterExamRequest,
    service: PracticeService = Depends(get_practice_service),
):
    videos = [v.model_dump() for v in body.videos]
    result = service.start_chapter_exam(
        body.studentId,
        body.chapterId,
        videos,
        course_id=body.courseId,
        course_title=body.courseTitle,
    )
    return ok(data=result, trace_id=get_trace_id())


@router.post("/submit")
async def submit_practice(
    body: SubmitPracticeRequest,
    service: PracticeService = Depends(get_practice_service),
):
    answers = [a.model_dump() for a in body.answers]
    result = service.submit_practice(body.practiceId, answers)
    return ok(data=result, trace_id=get_trace_id())


@router.post("/grade")
async def grade_practice(
    body: GradePracticeRequest,
    service: PracticeService = Depends(get_practice_service),
):
    answers = [a.model_dump() for a in body.answers]
    result = service.grade_practice(body.practiceId, answers)
    return ok(data=result, trace_id=get_trace_id())


@router.get("/history")
async def practice_history(
    studentId: str,
    sessionType: str | None = None,
    service: PracticeService = Depends(get_practice_service),
):
    result = service.get_history(studentId, sessionType)
    return ok(data=result, trace_id=get_trace_id())


@router.get("/{practiceId}")
async def get_practice(
    practiceId: str,
    service: PracticeService = Depends(get_practice_service),
):
    result = service.get_practice(practiceId)
    return ok(data=result, trace_id=get_trace_id())
