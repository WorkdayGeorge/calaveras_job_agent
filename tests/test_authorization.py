from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from web.app import BrowserSecurityMiddleware, require_admin


def fake_request(session):
    return SimpleNamespace(
        session=session,
        url=SimpleNamespace(path="/admin/analytics"),
    )


def test_regular_user_cannot_access_admin_routes():
    response = require_admin(fake_request({"user_id": "user-1", "role": "user"}))
    assert response.status_code == 403


def test_administrator_passes_admin_guard():
    assert require_admin(
        fake_request({"user_id": "admin-1", "role": "administrator"})
    ) is None


def test_cross_site_post_is_rejected():
    app = FastAPI()
    app.add_middleware(BrowserSecurityMiddleware)

    @app.post("/change")
    def change():
        return {"ok": True}

    client = TestClient(app)
    response = client.post(
        "/change",
        headers={"Origin": "https://malicious.example"},
    )
    assert response.status_code == 403


def test_security_headers_are_added():
    app = FastAPI()
    app.add_middleware(BrowserSecurityMiddleware)

    @app.get("/")
    def root(request: Request):
        return {"ok": True}

    response = TestClient(app).get("/")
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
