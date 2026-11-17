from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.infrastructure.observability.tracing import TraceIdMiddleware


def test_trace_id_generated_and_echoed():
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)

    @app.get("/x")
    def x():
        return {"ok": True}

    c = TestClient(app)
    r1 = c.get("/x")
    assert r1.headers.get("x-trace-id")  # 无请求头时生成
    r2 = c.get("/x", headers={"X-Trace-Id": "abc123"})
    assert r2.headers.get("x-trace-id") == "abc123"
