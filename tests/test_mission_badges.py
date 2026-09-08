import asyncio
import importlib.util
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.deps.auth import LoginUser, sign_access_token
from app.exceptions import ApiError
from app.main import app
from app.models import SubmissionStatus
from app.repositories.stamp_submission import StampSubmissionRepository
from app.services.stamp_submission import StampSubmissionService, get_stamp_submission_service
from app.services.badge_rules import badge_progress, earned_badge_rules, normalize_sport


def run(coro):
    return asyncio.run(coro)


class AsyncAdapter:
    """Run the repository's actual SQL on an isolated in-memory database."""

    def __init__(self, connection):
        self.connection = connection
        self.orm = Session(connection)

    async def execute(self, statement):
        return self.connection.execute(statement)

    async def scalars(self, statement):
        return self.orm.scalars(statement)

    def add(self, value):
        self.orm.add(value)

    async def flush(self):
        self.orm.flush()


@pytest.fixture
def database():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        for sql in (
            "CREATE TABLE courses (id INTEGER PRIMARY KEY, title TEXT, sport_name TEXT, is_published BOOLEAN)",
            "CREATE TABLE course_stamps (id INTEGER PRIMARY KEY, course_id INTEGER, stamp_id INTEGER)",
            "CREATE TABLE activities (id INTEGER PRIMARY KEY, sport_name TEXT, sigun TEXT, source TEXT, external_id TEXT)",
            "CREATE TABLE stamps (id INTEGER PRIMARY KEY, activity_id INTEGER, stamp_catalog_id INTEGER)",
            "CREATE TABLE stamp_catalog (id INTEGER PRIMARY KEY, sport_en TEXT)",
            "CREATE TABLE stamp_submissions (id INTEGER PRIMARY KEY, passport_id INTEGER, stamp_id INTEGER, status TEXT, is_demo BOOLEAN DEFAULT 0)",
            "CREATE TABLE collected_stamps (id INTEGER PRIMARY KEY, passport_id INTEGER, stamp_id INTEGER)",
            "CREATE TABLE badges (id INTEGER PRIMARY KEY, rule_key TEXT UNIQUE, image_url TEXT, description TEXT, created_at DATETIME, updated_at DATETIME)",
            "CREATE TABLE collected_badges (id INTEGER PRIMARY KEY, passport_id INTEGER, badge_id INTEGER, collected_at DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(passport_id, badge_id))",
        ):
            connection.execute(sa.text(sql))
        yield connection


def insert(connection, table, **values):
    columns = ", ".join(values)
    placeholders = ", ".join(f":{key}" for key in values)
    connection.execute(sa.text(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"), values)


def mission(connection, course_id, stamp_ids, *, published=True, sport=None, catalog=None, city="춘천시"):
    insert(connection, "courses", id=course_id, sport_name=sport, is_published=published)
    if catalog:
        connection.execute(sa.text("INSERT OR IGNORE INTO stamp_catalog (id, sport_en) VALUES (:id, :sport)"), {"id": course_id, "sport": catalog})
    for stamp_id in stamp_ids:
        # Sharing a stamp between missions is deliberate in one ambiguity test.
        connection.execute(sa.text("INSERT OR IGNORE INTO activities (id, sport_name, sigun) VALUES (:id, :sport, :city)"), {"id": stamp_id, "sport": sport, "city": city})
        connection.execute(sa.text("INSERT OR IGNORE INTO stamps (id, activity_id, stamp_catalog_id) VALUES (:id, :id, :catalog)"), {"id": stamp_id, "catalog": course_id if catalog else None})
        insert(connection, "course_stamps", course_id=course_id, stamp_id=stamp_id)


def proof(connection, stamp_id, *, passport=1, status="approved", demo=False):
    insert(connection, "stamp_submissions", stamp_id=stamp_id, passport_id=passport, status=status, is_demo=demo)


def progress(connection):
    facts = run(StampSubmissionRepository(AsyncAdapter(connection)).completed_mission_facts(1))
    counts = badge_progress(facts)
    return {name: counts[name] for name in ("missions", "mountains", "sports")}


def test_badges_count_distinct_fully_approved_missions_not_stamps_or_regions(database):
    mission(database, 1, [1], sport="zipline", catalog="MOUNTAIN")
    mission(database, 2, [2], sport="running", catalog="ATHLETICS")
    mission(database, 3, [3], sport="surfing", catalog="WATER")
    for stamp in (1, 2, 3):
        proof(database, stamp)
    proof(database, 1)  # A duplicated/re-submitted approval is still one mission.
    proof(database, 2, status="rejected")
    assert progress(database) == {"missions": 3, "mountains": 1, "sports": 3}
    # All three were in the same city. Geography is not the Explorer condition.
    assert database.execute(sa.text("SELECT COUNT(DISTINCT sigun) FROM activities")).scalar_one() == 1


def test_pending_rejected_drafts_admin_stamps_other_users_and_demo_do_not_count(database):
    for course_id in range(1, 8):
        mission(database, course_id, [course_id], sport="hiking", published=course_id != 3)
    proof(database, 1, status="pending")
    proof(database, 2, status="rejected")
    proof(database, 3)  # Draft course.
    proof(database, 4, passport=2)
    proof(database, 5, demo=True)
    insert(database, "collected_stamps", passport_id=1, stamp_id=6)
    proof(database, 7, status="pending")
    assert progress(database) == {
        "missions": 0, "mountains": 0, "sports": 0,
    }


def test_multi_stamp_course_completes_only_after_every_required_photo_is_approved(database):
    mission(database, 1, [1, 2], sport="hiking")
    proof(database, 1)
    proof(database, 2, status="pending")
    assert progress(database)["missions"] == 0
    proof(database, 2)
    assert progress(database) == {"missions": 1, "mountains": 1, "sports": 1}


def test_one_shared_stamp_cannot_turn_into_multiple_mission_completions(database):
    mission(database, 1, [1], sport="hiking")
    mission(database, 2, [1], sport="hiking")
    proof(database, 1)
    assert progress(database)["missions"] == 0


def test_awards_are_idempotent_and_scoped_to_passport(database):
    insert(database, "badges", id=10, rule_key="three_missions")
    insert(database, "badges", id=2, rule_key="first_mountain")
    adapter = AsyncAdapter(database)
    repository = StampSubmissionRepository(adapter)
    run(repository.award_badges(1, {"first_mountain", "three_missions"}))
    run(repository.award_badges(1, {"first_mountain", "three_missions"}))
    assert database.execute(sa.text("SELECT COUNT(*) FROM collected_badges WHERE passport_id=1")).scalar_one() == 2
    assert database.execute(sa.text("SELECT COUNT(*) FROM collected_badges WHERE passport_id=2")).scalar_one() == 0


@pytest.mark.parametrize("missions,mountains,expected", [
    (0, 0, set()),
    (1, 1, {"first_mission", "first_mountain"}),
    (2, 0, {"first_mission"}),
    (3, 0, {"first_mission", "three_missions"}),
])
def test_review_awards_requested_badges_at_exact_mission_thresholds(missions, mountains, expected):
    now = datetime(2026, 9, 8)
    row = SimpleNamespace(id=1, passport_id=2, stamp_id=3, object_key="proof", share_to_feed=False, feed_caption=None, status=SubmissionStatus.pending, reviewer_id=None, reviewed_at=None, rejection_reason=None, created_at=now, updated_at=now)

    class Repository:
        awarded = None

        async def get(self, _item_id):
            return row

        async def approve(self, value, _reviewer_id):
            value.status = SubmissionStatus.approved
            return value

        async def completed_mission_facts(self, _passport_id):
            return [{"course_id": i + 1, "mountain": i < mountains, "activity_sport": "golf"} for i in range(missions)]

        async def award_badges(self, passport_id, rules):
            assert passport_id == 2
            self.awarded = rules

    repository = Repository()
    run(StampSubmissionService(repository, SimpleNamespace(proof_url=lambda key: key)).review(1, LoginUser(9, "admin@example.com")))
    assert repository.awarded == expected


def load_migration():
    path = Path("alembic/versions/0038_mission_badge_catalog.py")
    spec = importlib.util.spec_from_file_location("mission_badge_catalog", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_catalog_migration_keeps_existing_badge_id_and_never_grants_badges(database, monkeypatch):
    insert(database, "badges", id=42, rule_key="three_regions", description="old Explorer")
    insert(database, "collected_badges", id=1, passport_id=7, badge_id=42)
    migration = load_migration()
    monkeypatch.setattr(migration.op, "get_bind", lambda: database)
    migration.upgrade()
    migration.upgrade()
    assert database.execute(sa.text("SELECT COUNT(*) FROM badges")).scalar_one() == 12
    assert database.execute(sa.text("SELECT id FROM badges WHERE rule_key='three_missions'")).scalar_one() == 42
    assert database.execute(sa.text("SELECT passport_id, badge_id FROM collected_badges")).all() == [(7, 42)]
    assert "미션 3개" in database.execute(sa.text("SELECT description FROM badges WHERE id=42")).scalar_one()


def test_catalog_migration_does_not_merge_existing_distinct_badge_records(database, monkeypatch):
    insert(database, "badges", id=42, rule_key="three_regions")
    insert(database, "badges", id=43, rule_key="three_missions")
    insert(database, "collected_badges", id=1, passport_id=7, badge_id=42)
    insert(database, "collected_badges", id=2, passport_id=7, badge_id=43)
    migration = load_migration()
    monkeypatch.setattr(migration.op, "get_bind", lambda: database)
    migration.upgrade()
    assert database.execute(sa.text("SELECT badge_id FROM collected_badges ORDER BY id")).scalars().all() == [42, 43]


def test_reject_and_repeated_review_never_grant_another_badge():
    now = datetime(2026, 9, 8)
    row = SimpleNamespace(id=1, passport_id=2, stamp_id=3, object_key="proof", share_to_feed=False, feed_caption=None, status=SubmissionStatus.pending, reviewer_id=None, reviewed_at=None, rejection_reason=None, created_at=now, updated_at=now)

    class Repository:
        async def get(self, item_id):
            return row

        async def reject(self, value, reviewer_id, reason):
            value.status = SubmissionStatus.rejected
            return value

        async def completed_mission_facts(self, _passport_id):
            raise AssertionError("Rejected reviews must not evaluate badges")

    service = StampSubmissionService(Repository(), SimpleNamespace(proof_url=lambda key: key))
    run(service.review(1, LoginUser(9, "admin@example.com"), "사진 조건 불충족"))
    with pytest.raises(ApiError) as failure:
        run(service.review(1, LoginUser(9, "admin@example.com")))
    assert failure.value.status == 409


def test_sport_aliases_are_normalized_before_multi_sports_and_specific_awards():
    assert normalize_sport(" hiking ") == normalize_sport("등산")
    assert normalize_sport("마라톤") == normalize_sport("RUNNING")
    facts = [{"course_id": i, "activity_sport": sport} for i, sport in enumerate(("hiking", "등산", "HIKING"), start=1)]
    assert badge_progress(facts)["sports"] == 1
    assert "three_sports" not in earned_badge_rules(facts)
    facts.extend([{"course_id": 4, "activity_sport": "마라톤"}, {"course_id": 5, "activity_sport": "cycling"}])
    assert {"three_sports", "first_running", "first_cycling"} <= earned_badge_rules(facts)


def test_generic_categories_do_not_award_water_subtypes_snow_or_special_proof_badges():
    facts = [
        {"course_id": 1, "course_sport": "WATER", "activity_sport": "water"},
        {"course_id": 2, "course_sport": "SNOW", "activity_sport": "ice_skating"},
        {"course_id": 3, "course_sport": "WATER", "activity_sport": "kayak"},
        {"course_id": 4, "course_sport": "WATER", "activity_sport": "sailing"},
        {"course_id": 5, "course_sport": "OLYMPIC", "activity_sport": "ski"},
        {"course_id": 6, "course_title": "설악산 1,708m 일출 명소 방문", "activity_sport": "hiking"},
        {"course_id": 7, "activity_sport": "scuba"},
        {"course_id": 8, "activity_sport": "windsurfing"},
        {"course_id": 9, "activity_sport": "wakeboard"},
        {"course_id": 10, "activity_sport": "waterski"},
    ]
    assert not {"first_marine", "first_inland_water", "first_snow", "summit_1000m", "first_sunrise"} & earned_badge_rules(facts)


def test_confirmed_26_mission_evidence_overrides_inaccurate_api_sport_categories():
    facts = [
        {"course_id": 3, "course_title": "아리힐스 짚와이어 체험 인증", "source": "tourapi", "external_id": "2777982", "activity_sport": "trekking", "mountain": True},
        {"course_id": 18, "course_title": "김유정 레일바이크 체험 인증", "source": "tourapi", "external_id": "1947118", "activity_sport": "trekking"},
        {"course_id": 19, "course_title": "정동진 레일바이크 체험 인증", "source": "tourapi", "external_id": "2396259", "activity_sport": "trekking"},
    ]
    assert badge_progress(facts)["trekking"] == 0
    assert badge_progress(facts)["sports"] == 2
    assert "trekking_three" not in earned_badge_rules(facts)
    assert "first_cycling" not in earned_badge_rules(facts)


def test_all_supported_badges_require_their_matching_completed_missions():
    facts = [
        {"course_id": 1, "activity_sport": "마라톤"},
        {"course_id": 2, "activity_sport": "zipline", "mountain": True},
        {"course_id": 3, "activity_sport": "스노보드"},
        {"course_id": 4, "activity_sport": "surfing"},
        {"course_id": 5, "activity_sport": "cycling"},
        {"course_id": 6, "activity_sport": "trekking"},
        {"course_id": 7, "activity_sport": "걷기"},
        {"course_id": 8, "activity_sport": "트래킹"},
        {"course_id": 11, "course_title": "물레길 카누 체험 인증", "source": "tourapi", "external_id": "1744974", "activity_sport": "kayak"},
    ]
    expected = {"first_mission", "first_mountain", "three_missions", "three_sports", "trekking_three", "first_marine", "first_inland_water", "first_snow", "first_cycling", "first_running"}
    assert earned_badge_rules(facts) == expected
    assert "trekking_three" not in earned_badge_rules(facts[:7])
    assert earned_badge_rules([facts[-1]]) == {"first_mission", "first_inland_water"}
    assert earned_badge_rules([facts[3]]) == {"first_mission", "first_marine"}


def test_review_and_direct_badge_awards_are_admin_only(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "mission-badge-permission-test")
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    user_token = sign_access_token(LoginUser(7, "member@example.com"))[0]

    class Service:
        async def review(self, *args, **kwargs):
            raise AssertionError("Unauthorized requests must not reach review")

    app.dependency_overrides[get_stamp_submission_service] = Service
    try:
        with TestClient(app) as client:
            assert client.post("/api/admin/stamp-submissions/1/approve").status_code == 401
            assert client.post("/api/admin/stamp-submissions/1/approve", headers={"Authorization": f"Bearer {user_token}"}).status_code == 403
            assert client.post("/api/collected-badges", headers={"Authorization": f"Bearer {user_token}"}, json={"passport_id": 1, "badge_id": 2}).status_code == 403
    finally:
        app.dependency_overrides.pop(get_stamp_submission_service, None)
