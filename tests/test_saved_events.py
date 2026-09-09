import asyncio
from datetime import datetime
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import mysql

from app.deps.auth import LoginUser, sign_access_token
from app.exceptions import ApiError
from app.main import app
from app.repositories.me import MeRepository
from app.services.me import MeService, get_me_service


def test_event_filter_is_applied_before_pagination_and_scoped_to_owner():
    queries = []

    class Session:
        async def execute(self, query):
            queries.append(query)
            return SimpleNamespace(all=lambda: [])

    repository = MeRepository(Session())
    asyncio.run(repository.saved_activities(7, offset=20, limit=20, events_only=True))
    asyncio.run(repository.saved_activities(7, offset=0, limit=100))
    sql = [str(query.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True})) for query in queries]
    assert "saved_activities.user_id = 7" in sql[0]
    assert "activities.category = 'event'" in sql[0]
    assert "ORDER BY saved_activities.created_at DESC, saved_activities.id DESC" in sql[0]
    assert queries[0]._offset_clause.value == 20 and queries[0]._limit_clause.value == 20
    assert "activities.category =" not in sql[1], "existing saved-state checks can still list every saved kind"
    assert "activities.is_active =" not in sql[0], "past/retired saved events are retained, not deleted"


def test_saved_event_service_preserves_original_activity_and_save_time():
    activity = SimpleNamespace(id=91, category="event", place_name="테스트 축제")
    row = SimpleNamespace(id=13, activity_id=91, created_at=datetime(2026, 9, 9))

    class Repository:
        async def saved_activities(self, user_id, **options):
            assert user_id == 7
            assert options == {"offset": 0, "limit": 3, "events_only": True}
            return [(row, activity)]

    response = asyncio.run(MeService(Repository(), None).saved_activities(LoginUser(7, "test@example.invalid"), offset=0, limit=3, events_only=True))
    assert response == [{"id": 13, "activity_id": 91, "created_at": row.created_at, "activity": activity}]
    assert "status" not in response[0], "saving an event does not award a collected status"


def test_saved_events_api_auth_query_validation_and_service_errors(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "saved-events-test-secret")
    token, _ = sign_access_token(LoginUser(7, "test@example.invalid"))
    calls = []

    class Service:
        async def saved_activities(self, actor, **options):
            calls.append((actor.id, options))
            if options["offset"] == 40:
                raise ApiError(503, "unavailable", "Saved events temporarily unavailable.")
            return []

    app.dependency_overrides[get_me_service] = Service
    try:
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {token}"}
            assert client.get("/api/me/saved-activities?eventsOnly=true").status_code == 401
            assert not calls
            result = client.get("/api/me/saved-activities?eventsOnly=true&page=2&size=20", headers=headers)
            assert result.status_code == 200 and result.json() == []
            assert calls[-1] == (7, {"offset": 20, "limit": 20, "events_only": True})
            assert client.get("/api/me/saved-activities", headers=headers).status_code == 200
            assert calls[-1][1]["events_only"] is False
            assert client.get("/api/me/saved-activities?eventsOnly=invalid", headers=headers).status_code == 400
            assert client.get("/api/me/saved-activities?size=0", headers=headers).status_code == 400
            failed = client.get("/api/me/saved-activities?eventsOnly=true&page=3&size=20", headers=headers)
            assert failed.status_code == 503 and failed.json()["error"] == "unavailable"
    finally:
        app.dependency_overrides.clear()


def test_demo_caption_migration_only_edits_exact_seeded_demo(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0042_shorten_demo_caption.py"
    spec = importlib.util.spec_from_file_location("demo_caption_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with create_engine("sqlite://").begin() as connection:
        connection.execute(text("CREATE TABLE stamp_submissions (id INTEGER PRIMARY KEY, is_demo INTEGER, object_key TEXT, feed_caption TEXT, updated_at TEXT)"))
        rows = [
            (1, 1, "operator-community-demo-v1", migration.OLD_CAPTION),
            (2, 0, "operator-community-demo-v1", migration.OLD_CAPTION),
            (3, 1, "another-demo", migration.OLD_CAPTION),
            (4, 1, "operator-community-demo-v1", "운영자가 직접 수정한 내용"),
        ]
        for row in rows:
            connection.execute(text("INSERT INTO stamp_submissions (id,is_demo,object_key,feed_caption) VALUES (:id,:demo,:key,:caption)"), dict(zip(["id", "demo", "key", "caption"], row, strict=True)))
        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        migration.upgrade()
        migration.upgrade()
        actual = connection.execute(text("SELECT id,is_demo,feed_caption FROM stamp_submissions ORDER BY id")).all()
        assert len(actual) == 4 and actual[0] == (1, 1, migration.NEW_CAPTION)
        assert actual[1][2] == actual[2][2] == migration.OLD_CAPTION
        assert actual[3][2] == rows[3][3]
        assert "[운영자 데모]" in actual[0][2]
        migration.downgrade()
        assert connection.execute(text("SELECT feed_caption FROM stamp_submissions WHERE id=1")).scalar_one() == migration.OLD_CAPTION
