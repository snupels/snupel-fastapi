import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import mysql

from app.deps.auth import LoginUser, sign_access_token
from app.exceptions import ApiError
from app.main import app
from app.models import Passport, Stamp, User
from app.repositories.auth import AuthRepository
from app.repositories.stampbook import StampbookRepository
from app.schemas.auth import AuthProvider
from app.schemas.stampbook import StampbookFilter
from app.services.auth import AuthService
from app.services.stampbook import StampbookService, get_stampbook_service


def test_create_user_also_creates_passport():
    class Session:
        def __init__(self):
            self.added = []

        def add(self, row):
            self.added.append(row)

        async def flush(self):
            if isinstance(self.added[0], User) and self.added[0].id is None:
                self.added[0].id = 7

        async def refresh(self, _row):
            pass

    session = Session()
    user = asyncio.run(
        AuthRepository(session).create_user(
            email="user@example.com",
            password_hash="hash",
        )
    )

    assert user.id == 7
    assert isinstance(session.added[1], Passport)
    assert session.added[1].user_id == 7


def test_create_user_propagates_passport_failure_for_transaction_rollback():
    class Session:
        def __init__(self):
            self.added = []
            self.flushes = 0

        def add(self, row):
            self.added.append(row)

        async def flush(self):
            self.flushes += 1
            if self.flushes == 1:
                self.added[0].id = 7
            else:
                raise RuntimeError("passport insert failed")

        async def refresh(self, _row):
            pass

    with pytest.raises(RuntimeError, match="passport insert failed"):
        asyncio.run(
            AuthRepository(Session()).create_user(
                email="user@example.com",
                password_hash="hash",
            )
        )


def test_oauth_creates_only_new_users(monkeypatch):
    class Repository:
        def __init__(self, existing=None):
            self.existing = existing
            self.created = 0
            self.linked = 0

        async def find_social_user(self, *_):
            return self.existing

        async def find_user_by_email(self, _email):
            return None

        async def create_user(self, **values):
            self.created += 1
            return SimpleNamespace(id=9, email=values["email"])

        async def create_social_account(self, **_values):
            self.linked += 1

    monkeypatch.setenv("JWT_SECRET", "stampbook-test-secret")
    monkeypatch.setattr("app.services.auth.is_allowed_redirect_uri", lambda _: True)
    monkeypatch.setattr(
        "app.services.auth.fetch_profile",
        lambda *_: ("provider-user", "oauth@example.com"),
    )
    body = SimpleNamespace(redirect_uri="https://sportspassport.kr/oauth", code="code")

    new = Repository()
    asyncio.run(AuthService(new).oauth_login(AuthProvider.google, body))
    assert (new.created, new.linked) == (1, 1)

    existing = Repository(SimpleNamespace(id=3, email="existing@example.com"))
    asyncio.run(AuthService(existing).oauth_login(AuthProvider.google, body))
    assert (existing.created, existing.linked) == (0, 0)


def test_stamp_catalog_connection_is_unique_and_sets_null_on_delete():
    constraint_names = {constraint.name for constraint in Stamp.__table__.constraints}
    foreign_key = next(
        key for key in Stamp.__table__.foreign_keys if key.target_fullname == "stamp_catalog.id"
    )

    assert "stamps_stamp_catalog_unique" in constraint_names
    assert foreign_key.ondelete == "SET NULL"


def test_stampbook_query_filters_by_owner_status_and_public_courses():
    statements = []

    class Result:
        def __init__(self, *, one=None, all_rows=None):
            self.one_row = one
            self.all_rows = all_rows

        def mappings(self):
            return self

        def one(self):
            return self.one_row

        def all(self):
            return self.all_rows

    class Session:
        async def execute(self, statement):
            statements.append(statement)
            if len(statements) == 1:
                return Result(one={"total": 90, "collected": 4, "available": 4, "locked": 82})
            return Result(all_rows=[])

    summary, rows = asyncio.run(
        StampbookRepository(Session()).stampbook(
            9,
            StampbookFilter.available,
            offset=15,
            limit=15,
        )
    )
    sql = [
        str(statement.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))
        for statement in statements
    ]

    assert summary == {"total": 90, "collected": 4, "available": 4, "locked": 82}
    assert rows == []
    assert "collected_stamps.passport_id = 9" in sql[0]
    assert "courses.is_published IS true" in sql[0]
    assert "status = 'available'" in sql[1]
    assert "LIMIT 15, 15" in sql[1]


def test_stampbook_service_groups_courses_and_uses_filtered_total(monkeypatch):
    class Repository:
        async def passport_id(self, user_id):
            assert user_id == 7
            return 2

        async def stampbook(self, passport_id, status, *, offset, limit):
            assert (passport_id, status, offset, limit) == (
                2,
                StampbookFilter.collected,
                0,
                15,
            )
            summary = {"total": 90, "collected": 1, "available": 4, "locked": 85}
            base = {
                "catalog_id": 1,
                "stamp_id": 10,
                "region_ko": "춘천",
                "region_en": "CHUNCHEON",
                "sport_ko": "산악",
                "sport_en": "MOUNTAIN",
                "color": "#2F6B4F",
                "image_key": "stamps/01-chuncheon-mountain.svg",
                "status": "collected",
                "collected_at": datetime(2026, 5, 15),
            }
            return summary, [
                base | {"course_id": 3, "course_title": "삼악산 트레일 챌린지"},
                base | {"course_id": 4, "course_title": "춘천 산악 코스"},
            ]

    monkeypatch.setenv("STAMP_IMAGE_BASE_URL", "https://assets.example.com")
    result = asyncio.run(
        StampbookService(Repository()).get(
            LoginUser(7, "user@example.com"),
            StampbookFilter.collected,
            page=1,
            size=15,
        )
    )

    assert result["total_items"] == 1
    assert result["total_pages"] == 1
    assert result["items"][0]["image_url"].startswith("https://assets.example.com/")
    assert [course["id"] for course in result["items"][0]["courses"]] == [3, 4]


def test_stampbook_service_rejects_missing_passport():
    class Repository:
        async def passport_id(self, _user_id):
            return None

    with pytest.raises(ApiError) as error:
        asyncio.run(
            StampbookService(Repository()).get(
                LoginUser(7, "user@example.com"),
                StampbookFilter.all,
                page=1,
                size=15,
            )
        )

    assert (error.value.status, error.value.code) == (404, "passport_not_found")


def test_stampbook_route_requires_login_and_defaults_to_fifteen(monkeypatch):
    class Service:
        async def get(self, actor, status, *, page, size):
            assert actor.id == 7
            assert (status, page, size) == (StampbookFilter.all, 1, 15)
            return {
                "summary": {"total": 90, "collected": 0, "available": 0, "locked": 90},
                "page": 1,
                "size": 15,
                "total_items": 90,
                "total_pages": 6,
                "items": [],
            }

    monkeypatch.setenv("JWT_SECRET", "stampbook-test-secret")
    app.dependency_overrides[get_stampbook_service] = Service
    token = sign_access_token(LoginUser(7, "user@example.com"))[0]
    try:
        with TestClient(app) as client:
            assert client.get("/api/me/stampbook").status_code == 401
            response = client.get(
                "/api/me/stampbook",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["totalItems"] == 90
    assert response.json()["totalPages"] == 6
