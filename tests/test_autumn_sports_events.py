import importlib.util
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa


@pytest.fixture
def migration():
    spec = importlib.util.spec_from_file_location(
        "autumn_events", Path("alembic/versions/0049_autumn_sports_events.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def database(migration):
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    table = sa.Table("activities", metadata, *[
        sa.Column(c.name, c.type, primary_key=c.name == "id")
        for c in migration._activities().c
    ])
    metadata.create_all(engine)
    with engine.begin() as connection:
        yield connection, table
    engine.dispose()


def test_catalog_is_idempotent_and_downgrade_preserves_saved_ids(migration, database, monkeypatch):
    connection, table = database
    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    migration.upgrade()
    before = list(connection.execute(sa.select(table).order_by(table.c.id)).mappings())
    assert len(before) == 4
    assert {e["sigun"] for e in before} == {"원주시", "동해시", "평창군", "인제군"}
    assert all(e["source"] is None and e["is_active"] for e in before)
    assert all(e["category"] == "event" and e["region"] == "강원특별자치도" for e in before)
    migration.upgrade()
    migration.downgrade()
    assert list(connection.execute(sa.select(table).order_by(table.c.id)).mappings()) == before


def test_matching_tourapi_record_keeps_original_data_and_image(migration, database):
    connection, table = database
    event = migration.PUBLIC_EVENTS[0]
    connection.execute(table.insert().values(event | {
        "category": "event", "source": "tourapi", "external_id": "upstream-id",
        "summary": "원문 그대로", "source_url": "https://example.com/original",
        "representative_image_url": "https://example.com/original.jpg",
        "metadata": {"contenttypeid": "15"},
        "starts_at": event["starts_at"].replace(hour=0),
    }))
    before = connection.execute(sa.select(table)).mappings().one()
    migration._upsert_event(connection, table, event)
    after = connection.execute(sa.select(table)).mappings().one()
    assert {k: v for k, v in after.items() if k != "metadata"} == {
        k: v for k, v in before.items() if k != "metadata"
    }
    assert after["metadata"]["contenttypeid"] == "15"
    assert after["metadata"]["participation"] == event["metadata"]["participation"]
    assert "imageCaption" not in after["metadata"]


def test_same_title_previous_year_and_non_event_are_not_duplicates(migration, database):
    connection, table = database
    event = migration.PUBLIC_EVENTS[0]
    connection.execute(table.insert(), [
        event | {"category": "event", "external_id": "previous-year",
                 "starts_at": event["starts_at"].replace(year=2025)},
        event | {"category": "sports", "external_id": "sports-place"},
    ])
    migration._upsert_event(connection, table, event)
    assert connection.scalar(sa.select(sa.func.count()).select_from(table)) == 3


def test_catalog_contains_official_evidence_and_no_expired_events(migration):
    ids = [e["external_id"] for e in migration.PUBLIC_EVENTS]
    assert len(set(ids)) == 4
    for event in migration.PUBLIC_EVENTS:
        assert datetime(2026, 10, 4) < event["starts_at"] < event["ends_at"]
        assert event["source_url"].startswith("https://")
        assert event["representative_image_url"].startswith("https://")
        metadata = event["metadata"]
        assert metadata["eventType"] == "sports"
        assert metadata["curationSource"] == "official_organizer"
        guide = metadata["participation"]
        assert event["source_url"] in guide["evidenceUrls"]
        assert guide["verifiedAt"] == "2026-10-04"
        assert guide["mode"] == "registration" and guide["status"] == "open"
        assert guide["fee"] and guide["registrationGuide"]
        for key in ("opensAt", "closesAt"):
            if key in guide:
                assert datetime.fromisoformat(guide[key]).utcoffset().total_seconds() == 32400


def test_latest_buldak_course_notice_overrides_older_press_release(migration):
    event = next(e for e in migration.PUBLIC_EVENTS if "buldak" in e["external_id"])
    guide = event["metadata"]["participation"]
    assert "5K(11:30)" in guide["programs"]
    assert "변경" in guide["note"]
