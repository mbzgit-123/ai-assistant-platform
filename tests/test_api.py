from fastapi.testclient import TestClient

from api.main import create_app


def test_health():
    c = TestClient(create_app())
    r = c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0 and body["message"] == "success"
    assert body["data"]["status"] == "ok"
    assert body["traceId"]


def test_ready():
    r = TestClient(create_app()).get("/ready")
    assert r.status_code == 200 and r.json()["code"] == 0
