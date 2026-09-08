import asyncio
import re
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.admin as admin_module
from app.admin import (
    ActivityAdmin,
    AdminAuth,
    CollectedStampAdmin,
    CourseAdmin,
    CourseStampAdmin,
    StampAdmin,
    SubmissionReviewAdmin,
    _review_reason,
    pending_codes,
)
from app.main import app
from app.models import (
    Activity,
    ActivityCategory,
    Course,
    Passport,
    Stamp,
    StampCatalog,
)
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


def test_activity_id_moves_to_collected_stamp_admin_view():
    assert "activity_id" not in StampAdmin().get_list_columns()
    assert "activity_id" in CollectedStampAdmin().get_list_columns()
    assert CollectedStampAdmin.form_columns == ["passport", "stamp", "collected_at"]


def test_primary_admin_forms_use_human_readable_relationships():
    assert CourseAdmin.form_columns[0] == "title"
    assert CourseStampAdmin.form_columns == ["course", "stamp", "position"]
    assert CollectedStampAdmin.form_columns == ["passport", "stamp", "collected_at"]
    mission_form = asyncio.run(CourseStampAdmin().scaffold_form())
    collected_form = asyncio.run(CollectedStampAdmin().scaffold_form())
    assert set(mission_form.__dict__) >= {"course", "stamp", "position"}
    assert set(collected_form.__dict__) >= {"passport", "stamp", "collected_at"}

    course = Course(id=3, title="강릉 바다 미션")
    passport = Passport(id=4, user_id=9, user_email="rookie@example.com")
    stamp = Stamp(id=5, activity_id=7, activity_label="경포해변")
    assert str(course) == "강릉 바다 미션 (#3)"
    assert str(passport) == "rookie@example.com의 패스포트 (#4)"
    assert str(stamp) == "경포해변 (스탬프 #5)"


def test_activity_admin_only_manages_events():
    view = ActivityAdmin()
    sql = str(view.list_query(SimpleNamespace()).compile(compile_kwargs={"literal_binds": True}))
    activity = Activity(category=ActivityCategory.tour)

    asyncio.run(view.on_model_change({}, activity, True, SimpleNamespace()))

    assert "activities.category = 'event'" in sql
    assert activity.category == ActivityCategory.event
    assert activity.source == "admin"


def test_submission_review_requires_reason_only_for_rejection():
    assert _review_reason("approve", "") is None
    assert _review_reason("reject", "  사진이 흐립니다.  ") == "사진이 흐립니다."

    for decision, reason in (("reject", " "), ("unknown", "사유")):
        try:
            _review_reason(decision, reason)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid review input must fail")


def test_submission_review_page_routes_approval_through_existing_service(monkeypatch):
    reviewed = []

    class Session:
        committed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def commit(self):
            self.committed = True

    class Service:
        def __init__(self, repository, storage):
            assert repository == "repository" and storage == "storage"

        async def review(self, item_id, actor, reason):
            reviewed.append((item_id, actor.id, reason))

    class Request:
        method = "POST"
        session = {"token": "token"}

        async def form(self):
            return {"submission_id": "12", "decision": "approve", "rejection_reason": ""}

    session = Session()
    monkeypatch.setattr(admin_module, "SessionLocal", lambda: session)
    monkeypatch.setattr(admin_module, "StampSubmissionRepository", lambda _: "repository")
    monkeypatch.setattr(admin_module, "StampSubmissionService", Service)
    monkeypatch.setattr(admin_module, "get_proof_storage", lambda: "storage")
    monkeypatch.setattr(
        admin_module, "verify_access_token", lambda _: SimpleNamespace(id=7, email="admin@example.com")
    )

    response = asyncio.run(SubmissionReviewAdmin.review.__wrapped__(SubmissionReviewAdmin(), Request()))

    assert response.status_code == 303
    assert reviewed == [(12, 7, None)]
    assert session.committed is True
