import asyncio
import importlib.util
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from app.repositories.activity import ActivityRepository


@pytest.fixture
def migration():
    path = Path("alembic/versions/0039_public_sports_events.py")
    spec = importlib.util.spec_from_file_location("public_sports_events_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def database(migration):
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    source = migration._activities()
    table = sa.Table("activities", metadata, *[
        sa.Column(column.name, column.type, primary_key=column.name == "id")
        for column in source.c
    ])
    metadata.create_all(engine)
    with engine.begin() as connection:
        yield connection, table
    engine.dispose()


def sample_event():
    return {
        "external_id": "official-2026-test-public-run",
        "place_name": "테스트 공개 러닝 행사",
        "sport_name": "러닝",
        "sigun": "춘천시",
        "address": "강원특별자치도 춘천시 테스트 장소",
        "starts_at": datetime(2026, 10, 11, 9),
        "ends_at": datetime(2026, 10, 11, 23, 59, 59),
        "summary": "테스트 참가 안내",
        "source_url": "https://organizer.example.com/event",
        "representative_image_url": "https://organizer.example.com/poster.jpg",
        "metadata": {"eventType": "sports", "officialSource": "테스트 주최자"},
    }


def test_repeated_migration_preserves_event_id_and_does_not_duplicate(migration, database):
    connection, table = database
    event = sample_event()
    migration._upsert_event(connection, table, event)
    initial = connection.execute(sa.select(table)).mappings().one()
    migration._upsert_event(connection, table, event)
    repeated = connection.execute(sa.select(table)).mappings().one()
    assert repeated == initial
    assert repeated["source"] is None
    assert repeated["last_synced_at"] is None
    assert repeated["is_active"] is True
    assert repeated["ends_at"].hour == 23


def test_verified_four_event_catalog_is_idempotent(migration, database, monkeypatch):
    connection, table = database
    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    migration.upgrade()
    original = list(connection.execute(sa.select(table).order_by(table.c.id)).mappings())
    assert len(original) == 4
    assert {row["external_id"] for row in original} == {
        "official-2026-roundlab-run", "official-2026-wonju-international-walking",
        "official-2026-uiamho-paddle-festa", "official-2026-yunseul-sunset-canoe",
    }
    assert all(row["source"] is None and row["is_active"] for row in original)
    assert all(row["category"] == "event" and row["region"] == "강원특별자치도" for row in original)
    assert all(row["latitude"] is None and row["longitude"] is None for row in original)
    migration.upgrade()
    assert list(connection.execute(sa.select(table).order_by(table.c.id)).mappings()) == original


def test_existing_tourapi_event_receives_only_supplemental_metadata(migration, database):
    connection, table = database
    event = sample_event()
    original = event | {
        "id": 471, "category": "event", "source": "tourapi", "external_id": "1234567",
        "summary": "공공 API 원문 소개", "source_url": "https://tourapi.example.com/guide",
        "representative_image_url": "https://tourapi.example.com/image.jpg",
        "starts_at": datetime(2026, 10, 11), "ends_at": datetime(2026, 10, 11),
        "metadata": {"contenttypeid": "15", "originalField": "preserved"},
        "last_synced_at": datetime(2026, 9, 8), "is_active": True,
    }
    connection.execute(table.insert().values(original))
    before = connection.execute(sa.select(table)).mappings().one()
    migration._upsert_event(connection, table, event)
    after = connection.execute(sa.select(table)).mappings().one()
    assert {key: value for key, value in after.items() if key != "metadata"} == {
        key: value for key, value in before.items() if key != "metadata"
    }
    assert after["metadata"] == original["metadata"] | event["metadata"]


def test_duplicate_api_image_does_not_inherit_caption_for_different_curated_photo(migration, database):
    connection, table = database
    event = sample_event()
    connection.execute(table.insert().values(event | {
        "category": "event", "source": "tourapi", "external_id": "public-api-123",
        "representative_image_url": "https://tourapi.example.com/different-image.jpg",
        "metadata": {"contenttypeid": "15"},
    }))
    event["metadata"] |= {"imageType": "photo", "imageCaption": "이전 행사 사진"}
    migration._upsert_event(connection, table, event)
    row = connection.execute(sa.select(table)).mappings().one()
    assert "imageCaption" not in row["metadata"]
    assert "imageType" not in row["metadata"]
    assert row["representative_image_url"] == "https://tourapi.example.com/different-image.jpg"


def test_same_title_different_year_or_non_event_does_not_block_new_event(migration, database):
    connection, table = database
    event = sample_event()
    connection.execute(table.insert(), [
        event | {"category": "event", "external_id": "official-2025-test-public-run",
                 "starts_at": datetime(2025, 10, 11)},
        event | {"category": "sports", "external_id": "sports-test-facility"},
    ])
    migration._upsert_event(connection, table, event)
    assert connection.scalar(sa.select(sa.func.count()).select_from(table)) == 3


def test_existing_metadata_updates_do_not_change_or_delete_unrelated_events(migration, database, monkeypatch):
    connection, table = database
    event = sample_event()
    connection.execute(table.insert(), [
        event | {"category": "event", "metadata": {"old": "keep"}},
        event | {"category": "event", "external_id": "unrelated-festival", "place_name": "다른 축제"},
    ])
    before = list(connection.execute(sa.select(table).order_by(table.c.id)).mappings())
    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    monkeypatch.setattr(migration, "EXISTING_EVENT_METADATA", {event["external_id"]: {"new": "guidance"}})
    monkeypatch.setattr(migration, "PUBLIC_EVENTS", ())
    migration.upgrade()
    after = list(connection.execute(sa.select(table).order_by(table.c.id)).mappings())
    assert after[0]["metadata"] == {"old": "keep", "new": "guidance"}
    assert after[1] == before[1]
    migration.downgrade()
    assert list(connection.execute(sa.select(table).order_by(table.c.id)).mappings()) == after


def test_three_existing_events_keep_their_ids_images_and_dates(migration, database, monkeypatch):
    connection, table = database
    external_ids = list(migration.EXISTING_EVENT_METADATA)
    originals = [sample_event() | {
        "id": 3269 + index, "category": "event", "source": None,
        "external_id": external_id, "metadata": {"eventType": "sports", "oldField": "preserve"},
    } for index, external_id in enumerate(external_ids)]
    connection.execute(table.insert(), originals)
    before = list(connection.execute(sa.select(table).order_by(table.c.id)).mappings())
    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    monkeypatch.setattr(migration, "PUBLIC_EVENTS", ())
    migration.upgrade()
    after = list(connection.execute(sa.select(table).order_by(table.c.id)).mappings())
    for old, updated in zip(before, after, strict=True):
        assert {key: value for key, value in updated.items() if key != "metadata"} == {
            key: value for key, value in old.items() if key != "metadata"
        }
        assert updated["metadata"]["oldField"] == "preserve"
        assert updated["metadata"]["eventType"] == "sports"
        participation = updated["metadata"]["participation"]
        assert participation["verifiedAt"] == "2026-09-08"
        assert participation["status"] != "open"
        assert participation["evidenceUrls"]


def test_curated_event_metadata_uses_explicit_sources_and_korean_timezone(migration):
    ids = set()
    for event in migration.PUBLIC_EVENTS:
        assert event["external_id"] not in ids
        ids.add(event["external_id"])
        assert event["external_id"].startswith("official-2026-")
        assert event["starts_at"] <= event["ends_at"]
        assert event["source_url"].startswith("https://")
        metadata = event["metadata"]
        assert metadata["officialSource"]
        assert metadata["curationSource"] == "official_organizer"
        assert metadata["eventType"] == "sports"
        participation = metadata["participation"]
        assert participation["mode"] in {"registration", "onsite", "spectator"}
        assert participation["status"] in {"open", "closed", "check"}
        assert participation["evidenceUrls"]
        assert participation["verifiedAt"] == "2026-09-08"
        for key in ("opensAt", "closesAt"):
            if key in participation:
                assert participation[key].endswith("+09:00")
                assert datetime.fromisoformat(participation[key]).utcoffset().total_seconds() == 32400


@pytest.mark.parametrize(("source", "category", "keep_curated"), [
    ("tourapi", "event", True), ("tourapi", "tour", False), ("durunubi", "event", False),
])
def test_sync_retains_only_curated_event_metadata(source, category, keep_curated):
    curated = {
        "participation": {"mode": "registration", "status": "check", "verifiedAt": "2026-09-08"},
        "officialSource": "공식 주최자", "eventType": "sports",
        "curationSource": "official_organizer",
        "imageType": "photo", "imageCaption": "이전 행사 사진",
    }
    row = SimpleNamespace(external_id="123", source_metadata=curated | {"cat3": "old", "stale": "discard"})

    class Session:
        async def scalars(self, _query):
            return [row]

        async def flush(self):
            pass

    now = datetime(2026, 9, 9)
    result = asyncio.run(ActivityRepository(Session()).sync_source(source, [{
        "external_id": "123", "category": category,
        "summary": "새 API 소개", "source_metadata": {"cat3": "new", "tel": "033-000-0000"},
    }], now))
    expected = {"cat3": "new", "tel": "033-000-0000"} | (curated if keep_curated else {})
    assert result == 1
    assert row.source_metadata == expected
    assert row.summary == "새 API 소개"
    assert row.source == source
    assert row.last_synced_at == now


def test_sync_refreshes_ordinary_upstream_official_source_instead_of_preserving_it():
    row = SimpleNamespace(external_id="123", source_metadata={
        "officialSource": "이전 API 주최자", "eventType": "sports",
        "participation": {"status": "open"}, "curationSource": "upstream",
    })

    class Session:
        async def scalars(self, _query):
            return [row]

        async def flush(self):
            pass

    updated = {"officialSource": "새 API 주최자", "eventType": "festival", "contenttypeid": "15"}
    asyncio.run(ActivityRepository(Session()).sync_source("tourapi", [{
        "external_id": "123", "category": "event", "source_metadata": updated,
    }], datetime(2026, 9, 9)))
    assert row.source_metadata == updated
    assert "participation" not in row.source_metadata
    assert "curationSource" not in row.source_metadata


@pytest.mark.parametrize(("curation_source", "image", "keep_caption"), [
    ("official_organizer", "original.jpg", True),
    ("official_organizer", "new-api-image.jpg", False),
    ("unverified", "original.jpg", False),
])
def test_sync_preserves_photo_caption_only_for_verified_same_image(curation_source, image, keep_caption):
    row = SimpleNamespace(
        external_id="123", representative_image_url="original.jpg",
        source_metadata={"curationSource": curation_source, "imageType": "photo", "imageCaption": "이전 행사"},
    )

    class Session:
        async def scalars(self, _query):
            return [row]

        async def flush(self):
            pass

    asyncio.run(ActivityRepository(Session()).sync_source("tourapi", [{
        "external_id": "123", "category": "event", "representative_image_url": image,
        "source_metadata": {"contenttypeid": "15"},
    }], datetime(2026, 9, 9)))
    assert ("imageCaption" in row.source_metadata) is keep_caption
    assert ("imageType" in row.source_metadata) is keep_caption
    assert row.representative_image_url == image
