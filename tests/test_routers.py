import asyncio
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import mysql

from app.deps.auth import LoginUser, sign_access_token
from app.exceptions import ApiError
from app.main import app
from app.repositories.activity import ActivityRepository
from app.services.activity import get_activity_service
from app.services.badge import get_badge_service
from app.services.collected_badge import get_collected_badge_service
from app.services.collected_stamp import get_collected_stamp_service
from app.services.course import get_course_service
from app.services.passport import get_passport_service

NOW = datetime(2026, 1, 1).isoformat()


class FakeService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    async def create(self, _body, _actor):
        if self.error:
            raise self.error
        return self.result

    async def list(self, _actor, *, offset, limit):
        self.pagination = (offset, limit)
        return self.result


CASES = [
    (
        "/api/badges",
        get_badge_service,
        True,
        {"description": "badge"},
        {"id": 1, "image_url": None, "description": "badge", "created_at": NOW, "updated_at": NOW},
    ),
    (
        "/api/activities",
        get_activity_service,
        True,
        {"category": "sports", "sport_name": "hiking"},
        {"id": 1, "category": "sports", "representative_image_url": None, "sport_name": "hiking", "region": None, "place_name": None, "latitude": None, "longitude": None, "created_at": NOW, "updated_at": NOW},
    ),
    (
        "/api/courses",
        get_course_service,
        True,
        {"theme": "healing"},
        {"id": 1, "recommended_companion": None, "representative_image_url": None, "estimated_duration_minutes": None, "theme": "healing", "created_at": NOW, "updated_at": NOW},
    ),
    (
        "/api/passports",
        get_passport_service,
        False,
        {"user_id": 7},
        {"id": 1, "user_id": 7, "created_at": NOW, "updated_at": NOW},
    ),
    (
        "/api/collected-badges",
        get_collected_badge_service,
        False,
        {"passport_id": 1, "badge_id": 2},
        {"id": 1, "passport_id": 1, "badge_id": 2, "collected_at": NOW},
    ),
    (
        "/api/collected-stamps",
        get_collected_stamp_service,
        True,
        {"passport_id": 1, "stamp_id": 2},
        {"id": 1, "passport_id": 1, "stamp_id": 2, "collected_at": NOW},
    ),
]


def token(email: str) -> str:
    return sign_access_token(LoginUser(7, email))[0]


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "router-test-secret")
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.mark.parametrize("path,dependency,admin,body,result", CASES)
def test_router_success_validation_auth_and_service_errors(path, dependency, admin, body, result):
    headers = {"Authorization": f"Bearer {token('admin@example.com' if admin else 'user@example.com')}"}
    app.dependency_overrides[dependency] = lambda: FakeService(result=result)

    with TestClient(app) as client:
        success = client.post(path, json=body, headers=headers)
        assert success.status_code == 201

        invalid = client.post(path, json={}, headers=headers)
        assert invalid.status_code == 400
        assert invalid.json() == {"error": "bad_request", "message": "Invalid request body."}

        assert client.post(path, json=body).status_code == 401
        if admin:
            user_headers = {"Authorization": f"Bearer {token('user@example.com')}"}
            assert client.post(path, json=body, headers=user_headers).status_code == 403

        app.dependency_overrides[dependency] = lambda: FakeService(
            error=ApiError(409, "conflict", "Already exists.")
        )
        conflict = client.post(path, json=body, headers=headers)
        assert conflict.status_code == 409
        assert conflict.json() == {"error": "conflict", "message": "Already exists."}


def test_health_and_openapi():
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.get("/api/docs").status_code == 200


def test_list_pagination_defaults_limits_and_openapi():
    service = FakeService(result=[])
    app.dependency_overrides[get_badge_service] = lambda: service

    with TestClient(app) as client:
        assert client.get("/api/badges").json() == []
        assert service.pagination == (0, 20)
        assert client.get("/api/badges?page=3&size=10").status_code == 200
        assert service.pagination == (20, 10)
        assert client.get("/api/badges?size=101").status_code == 400

        for operations in client.get("/api/docs").json()["paths"].values():
            operation = operations.get("get")
            if not operation:
                continue
            schema = operation["responses"].get("200", {}).get("content", {}).get(
                "application/json", {}
            ).get("schema", {})
            if schema.get("type") != "array":
                continue
            parameters = {item["name"]: item["schema"] for item in operation["parameters"]}
            assert parameters["page"]["default"] == 1
            assert parameters["size"]["default"] == 20
            assert parameters["size"]["maximum"] == 100


def test_activity_pagination_compiles_for_mysql_with_mission_filters():
    statements = []

    class Result:
        def all(self):
            return []

    class Session:
        async def execute(self, statement):
            statements.append(statement)
            return Result()

    repository = ActivityRepository(Session())
    for mission in (True, False):
        asyncio.run(
            repository.explore(
                region=None, sport=None, theme=None, mission=mission, offset=20, limit=20
            )
        )

    sql = [
        str(statement.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))
        for statement in statements
    ]
    assert all("LIMIT 20, 20" in statement for statement in sql)
    assert "EXISTS" in sql[0] and "NOT (EXISTS" in sql[1]
