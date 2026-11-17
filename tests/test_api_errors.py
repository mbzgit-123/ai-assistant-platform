from fastapi import APIRouter
from fastapi.testclient import TestClient

from api.main import create_app
from shared.common.exception.base import NotFoundError
import api.main as main_module


def test_app_exception_mapped():
    app = create_app()

    @app.get("/boom")
    def boom():
        raise NotFoundError("missing")

    r = TestClient(app).get("/boom")
    assert r.status_code == 404
    assert r.json()["code"] == 40400
