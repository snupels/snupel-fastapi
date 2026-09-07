import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, text


def test_hiking_migration_is_repeatable_and_preserves_existing_rows(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "verified_hiking", Path("alembic/versions/0034_verified_hiking.py")
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with create_engine("sqlite://").begin() as connection:
        connection.execute(text(
            "CREATE TABLE activities (id INTEGER PRIMARY KEY, category TEXT, sport_name TEXT, "
            "region TEXT, sigun TEXT, place_name TEXT, address TEXT, summary TEXT, "
            "source_url TEXT, external_id TEXT, metadata TEXT, is_active INTEGER, "
            "created_at TEXT, updated_at TEXT)"
        ))
        connection.execute(text(
            "INSERT INTO activities (external_id, place_name, is_active) "
            "VALUES ('existing', '기존 장소', 1)"
        ))
        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        migration.upgrade()
        migration.upgrade()
        rows = connection.execute(text(
            "SELECT * FROM activities WHERE external_id LIKE 'verified-hiking-%'"
        )).mappings().all()
        assert len(rows) == 5
        for row in rows:
            assert row["category"] == "sports"
            assert row["sport_name"] == "hiking"
            assert row["place_name"] and row["address"]
            assert "→" in row["summary"] and "통제" in row["summary"]
            assert "knps.or.kr" in row["source_url"]
        migration.downgrade()
        assert connection.execute(text(
            "SELECT count(*) FROM activities WHERE is_active = 1"
        )).scalar_one() == 1
