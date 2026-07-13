import asyncio
import re
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.admin as admin_module
from app.admin import AdminAuth, pending_codes
from app.main import app


def test_admin_requires_login():
    with TestClient(app) as client:
        response = client.get("/admin/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/login")


def test_admin_password_then_single_use_email_code(monkeypatch):
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def scalar(self, _):
            return SimpleNamespace(id=7, email="admin@example.com", password_hash="hash")

    class Request:
        session = {}
        values = {"username": "admin@example.com", "password": "password"}

        async def form(self):
            return self.values

    sent = []
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setattr(admin_module, "SessionLocal", Session)
    monkeypatch.setattr(admin_module, "password_hasher", SimpleNamespace(verify=lambda *_: True))
    monkeypatch.setattr(admin_module, "send_mail", lambda *args: sent.append(args))
    pending_codes.clear()
    request = Request()
    auth = AdminAuth("test-secret")

    response = asyncio.run(auth.login(request))
    code = re.search(r"\d{6}", sent[0][2]).group()
    assert response.status_code == 302
    assert request.session == {"pending_admin_email": "admin@example.com"}

    request.values = {"code": code}
    assert asyncio.run(auth.login(request)) is True
    assert "token" in request.session
    assert not pending_codes
