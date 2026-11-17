from fastapi.testclient import TestClient

from api.main import create_app
from shared.common.exception.base import NotFoundError


def test_app_exception_mapped():
    app = create_app()

    @app.get("/boom")
    def boom():
        raise NotFoundError("missing")

    r = TestClient(app).get("/boom")
    assert r.status_code == 404
    assert r.json()["code"] == 40400


def test_app_exception_includes_trace_id_and_data():
    app = create_app()

    @app.get("/boom2")
    def boom2():
        raise NotFoundError("missing")

    body = TestClient(app).get("/boom2").json()
    assert body["code"] == 40400
    assert body["traceId"]
    assert body["data"] is None


def test_http_404_returns_unified_shape():
    r = TestClient(create_app()).get("/nonexistent")
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == 40400
    assert body["traceId"]
    assert body["data"] is None
