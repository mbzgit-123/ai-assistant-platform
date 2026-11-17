from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared.common.exception.base import AppException
from shared.common.exception.codes import ErrorCode
from shared.infrastructure.observability.logging import get_logger
from shared.infrastructure.observability.tracing import get_trace_id

logger = get_logger("api")


def _error_response(status_code: int, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "data": None,
            "traceId": get_trace_id(),
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(request: Request, exc: AppException) -> JSONResponse:
        return _error_response(exc.http_status, exc.code.value, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(400, ErrorCode.BAD_REQUEST.value, "invalid request")

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        if exc.status_code == 404:
            code = ErrorCode.NOT_FOUND.value
        elif 400 <= exc.status_code < 500:
            code = ErrorCode.BAD_REQUEST.value
        else:
            code = ErrorCode.INTERNAL.value
        return _error_response(exc.status_code, code, "http error")

    @app.exception_handler(Exception)
    async def handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error", trace_id=get_trace_id())
        return _error_response(500, ErrorCode.INTERNAL.value, "internal error")
