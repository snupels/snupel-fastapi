import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text


@pytest.fixture
def migration():
    path = Path("alembic/versions/0033_photo_missions.py")
    spec = importlib.util.spec_from_file_location("photo_missions", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_catalog_has_24_distinct_regional_rewards(migration):
    missions = migration.MISSIONS
    assert len(missions) == 24
    assert len({(m["region"], m["sport"]) for m in missions}) == 24
    assert len({m["title"] for m in missions}) == 24
    assert {m["sport"] for m in missions} == {"MOUNTAIN", "SNOW", "WATER", "ATHLETICS", "OLYMPIC"}
    assert all("1장" in m["proof"] for m in missions)
    assert all("동계" in m["schedule"] for m in missions if m["sport"] == "SNOW")
    assert ("평창", "OLYMPIC") not in {(m["region"], m["sport"]) for m in missions}
    assert ("홍천", "ATHLETICS") not in {(m["region"], m["sport"]) for m in missions}


def test_migration_links_real_places_and_is_repeatable(migration, monkeypatch):
    with create_engine("sqlite://").begin() as connection:
        for sql in [
            "CREATE TABLE activities (id INTEGER PRIMARY KEY, source TEXT, external_id TEXT, "
            "is_active INTEGER, representative_image_url TEXT)",
            "CREATE TABLE stamp_catalog (id INTEGER PRIMARY KEY, region_ko TEXT, sport_en TEXT)",
            "CREATE TABLE stamps (id INTEGER PRIMARY KEY, stamp_catalog_id INTEGER, "
            "activity_id INTEGER, description TEXT, image_url TEXT, updated_at TEXT)",
            "CREATE TABLE courses (id INTEGER PRIMARY KEY, category TEXT, sport_name TEXT, "
            "recommended_companion TEXT, representative_image_url TEXT, estimated_duration_minutes "
            "INTEGER, theme TEXT, title TEXT, description TEXT, is_published INTEGER, "
            "created_at TEXT, updated_at TEXT)",
            "CREATE TABLE course_stamps (course_id INTEGER, stamp_id INTEGER, "
            "position INTEGER, created_at TEXT)",
        ]:
            connection.execute(text(sql))
        for number, mission in enumerate(migration.MISSIONS, 1):
            params = {**mission, "number": number}
            connection.execute(text("INSERT INTO activities VALUES "
                                    "(:activityId, :source, :externalId, 1, 'photo.jpg')"), params)
            connection.execute(text("INSERT INTO stamp_catalog VALUES "
                                    "(:number, :region, :sport)"), params)
            connection.execute(text("INSERT INTO stamps VALUES "
                                    "(:number, :number, 9999, '', 'catalog.svg', NULL)"), params)
        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        migration.upgrade()
        migration.upgrade()
        assert connection.scalar(text("SELECT COUNT(*) FROM courses")) == 24
        assert connection.scalar(text("SELECT COUNT(*) FROM course_stamps")) == 24
        assert connection.scalar(text("SELECT COUNT(*) FROM stamps WHERE activity_id = 9999")) == 0
        assert connection.scalar(text("SELECT COUNT(*) FROM stamps WHERE image_url = 'catalog.svg'")) == 24
        assert connection.scalar(text("SELECT COUNT(*) FROM courses WHERE is_published = 1")) == 24
        connection.execute(text("UPDATE courses SET title = '다른 기존 미션' WHERE id = 1"))
        with pytest.raises(RuntimeError, match="another mission"):
            migration.upgrade()
