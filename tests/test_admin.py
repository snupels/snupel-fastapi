import asyncio
import re
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.admin as admin_module
from app.admin import AdminAuth, pending_codes
from app.main import app
from app.models import Activity, Stamp, StampCatalog
from app.repositories.stamp import StampRepository


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


def test_stamp_seed_creates_missing_rows_and_fixes_image_keys(monkeypatch):
    catalog = StampCatalog(
        id=1,
        region_ko="춘천",
        region_en="CHUNCHEON",
        sport_ko="산악",
        sport_en="MOUNTAIN",
        color="#2F6B4F",
        image_key="stamps/05-chuncheon-mountain.svg",
    )

    class Session:
        def __init__(self):
            self.calls = 0
            self.added = []

        async def scalars(self, _statement):
            self.calls += 1
            return [catalog] if self.calls == 1 else []

        def add(self, row):
            self.added.append(row)

        async def flush(self):
            for row in self.added:
                if isinstance(row, Activity) and row.id is None:
                    row.id = 7

    monkeypatch.setenv(
        "STAMP_IMAGE_BASE_URL",
        "https://sportspassport-asset.s3.ap-northeast-2.amazonaws.com",
    )
    session = Session()
    result = asyncio.run(StampRepository(session).seed_catalog())

    assert result == {"created": 1, "existing": 0, "total": 1}
    assert catalog.image_key == "stamps/01-chuncheon-mountain.svg"
    activity, stamp = session.added
    assert activity.external_id == "stamp-catalog-1"
    assert isinstance(stamp, Stamp)
    assert stamp.activity_id == 7 and stamp.stamp_catalog_id == 1
    assert stamp.image_url.endswith("/stamps/01-chuncheon-mountain.svg")
