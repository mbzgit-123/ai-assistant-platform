import contextvars
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default=""
)


def get_trace_id() -> str:
    return _trace_id_var.get()


class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        trace_id = request.headers.get("X-Trace-Id")
        if not trace_id:
            trace_id = uuid.uuid4().hex
        token = _trace_id_var.set(trace_id)
        try:
            response = await call_next(request)
        finally:
            _trace_id_var.reset(token)
        response.headers["X-Trace-Id"] = trace_id
        return response
