import asyncio
import importlib.util

from sqlalchemy import create_engine, text

from app.jobs.sync_tourism import TourismSync, tourism_item


def test_only_api_places_with_route_guidance_become_hiking():
    calls = []

    class Sync(TourismSync):
        async def _get(self, url, params):
            calls.append((url, params))
            details = [{"infoname": "등산로", "infotext": "입구 → 정상<br>왕복 4km"}]
            if params["contentId"] == "2":
                details = [{"infoname": "주차장", "infotext": "있음"}]
            return {"response": {"body": {"items": {"item": details}, "totalCount": 1}}}

    rows = [
        {"contentid": str(i), "contenttypeid": "12", "title": name, "addr1": address}
        for i, name, address in [
            (1, "테스트산", "강원특별자치도 평창군"),
            (2, "설명없는산", "강원특별자치도 평창군"),
            (3, "위치없는산", ""), (4, "일반 둘레길", "강원특별자치도 원주시"),
        ]
    ]
    asyncio.run(Sync(None, None, "test-key")._fill_hiking_routes(rows, {}))
    result = tourism_item(rows[0])
    assert result["category"] == "sports" and result["sport_name"] == "hiking"
    assert result["place_name"] == "테스트산"  # Never invent a course title.
    assert result["summary"] == "등산로\n입구 → 정상\n왕복 4km"
    assert result["source_metadata"]["hiking_routes"][0]["infotext"].endswith("<br>왕복 4km")
    assert all(tourism_item(row)["category"] == "tour" for row in rows[1:])
    assert len(calls) == 2 and all(url.endswith("/detailInfo2") for url, _ in calls)


def test_manual_routes_are_unpublished_not_deleted(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "remove_curated", "alembic/versions/0035_remove_curated_hiking.py"
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with create_engine("sqlite://").begin() as connection:
        connection.execute(text("CREATE TABLE activities "
                                "(source TEXT, external_id TEXT, is_active INTEGER, updated_at TEXT)"))
        for key in migration.KEYS:
            connection.execute(text("INSERT INTO activities VALUES (NULL, :key, 1, NULL)"),
                               {"key": key})
        connection.execute(text("INSERT INTO activities VALUES ('tourapi', 'existing', 1, NULL)"))
        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        migration.upgrade()
        migration.upgrade()
        assert connection.execute(text("SELECT count(*) FROM activities")).scalar_one() == 6
        assert connection.execute(text(
            "SELECT external_id FROM activities WHERE is_active = 1"
        )).scalar_one() == "existing"
