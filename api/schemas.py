from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int
    message: str
    data: T | None = None
    traceId: str | None = None


def ok(data: Any = None, trace_id: str | None = None) -> ApiResponse:
    return ApiResponse(code=0, message="success", data=data, traceId=trace_id)
