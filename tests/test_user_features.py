import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import mysql

from app.deps.auth import LoginUser, sign_access_token
from app.exceptions import ApiError
from app.main import app
from app.models import Base, RewardClaimStatus, RewardMilestone, SubmissionStatus
from app.repositories.me import MeRepository
from app.services.collected import CollectedService
from app.services.me import HISTORY_CODES, MeService, get_me_service
from app.services.passport import PassportService
from app.services.stamp_submission import StampSubmissionService

NOW = datetime(2026, 1, 1)


class Storage:
    @staticmethod
    def proof_url(key):
        return f"https://proof.example/{key}"


def run(coro):
    return asyncio.run(coro)


def test_personal_detail_services_allow_only_owner_or_admin(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    passport = SimpleNamespace(id=4, user_id=7)

    class Passports:
        async def get(self, _item_id):
            return passport

    owner = LoginUser(7, "owner@example.com")
    admin = LoginUser(9, "admin@example.com")
    stranger = LoginUser(8, "stranger@example.com")
    service = PassportService(Passports())
    assert run(service.get(4, owner)) is passport
    assert run(service.get(4, admin)) is passport
    with pytest.raises(ApiError) as error:
        run(service.get(4, stranger))
    assert error.value.status == 403

    class Collected:
        target_field = "stamp_id"

        async def get(self, _item_id):
            return SimpleNamespace(id=3, passport_id=4)

        async def owner_id(self, _row):
            return 7

    collected = CollectedService(Collected(), "Stamp")
    assert run(collected.get(3, owner)).id == 3
    with pytest.raises(ApiError) as error:
        run(collected.get(3, stranger))
    assert error.value.status == 403


def test_submission_approval_awards_all_satisfied_badges_in_same_service_flow():
    row = SimpleNamespace(
        id=1,
        passport_id=2,
        stamp_id=3,
        object_key="proofs/2/3/x.jpg",
        share_to_feed=False,
        feed_caption=None,
        status=SubmissionStatus.pending,
        reviewer_id=None,
        reviewed_at=None,
        rejection_reason=None,
        created_at=NOW,
        updated_at=NOW,
    )

    class Repository:
        async def get(self, _item_id):
            return row

        async def approve(self, value, reviewer_id):
            value.status = SubmissionStatus.approved
            value.reviewer_id = reviewer_id
            value.reviewed_at = NOW
            return value

        async def completed_mission_facts(self, passport_id):
            assert passport_id == 2
            return [
                {"course_id": 1, "mountain": True, "activity_sport": "zipline"},
                {"course_id": 2, "activity_sport": "golf"},
                {"course_id": 3, "activity_sport": "swimming"},
            ]

        async def award_badges(self, passport_id, rules):
            self.awarded = passport_id, rules

    repository = Repository()
    result = run(StampSubmissionService(repository, Storage()).review(1, LoginUser(9, "a@b.c")))
    assert result["status"] == SubmissionStatus.approved
    assert repository.awarded == (
        2,
        {"first_mission", "first_mountain", "three_missions", "three_sports"},
    )


def test_activity_history_has_stable_ids_search_filter_and_global_pagination():
    def item(source_id, when, **extra):
        return {
            "source_id": source_id,
            "activity_id": source_id,
            "course_id": None,
            "title": f"item {source_id}",
            "place_name": "춘천",
            "sigun": "춘천시",
            "image_url": None,
            "occurred_at": when,
        } | extra

    class Repository:
        async def activity_history(self, user_id, *, q, status, limit):
            assert (user_id, q, status, limit) == (7, "스키", "collected", 2)
            return [
                [],
                [item(2, NOW + timedelta(days=2))],
                [item(3, NOW + timedelta(days=1))],
            ]

        async def activity_history_item(self, user_id, kind, source_id):
            assert (user_id, kind, source_id) == (7, "saved", 3)
            return item(3, NOW)

    service = MeService(Repository(), Storage())
    rows = run(
        service.activity_history(
            LoginUser(7, "u@example.com"),
            q=" 스키 ",
            status="collected",
            offset=0,
            limit=2,
        )
    )
    assert [row["id"] for row in rows] == [22, 33]
    assert rows[0]["status"] == "collected"
    detail = run(service.activity_history_item(3 * 10 + HISTORY_CODES["saved"], LoginUser(7, "u@example.com")))
    assert detail["type"] == "saved" and detail["activity_id"] == 3


def test_activity_history_queries_join_owner_sources_and_apply_filters():
    statements = []

    class Result:
        def mappings(self):
            return self

        def all(self):
            return []

    class Session:
        async def execute(self, statement):
            statements.append(statement)
            return Result()

    run(MeRepository(Session()).activity_history(7, q="스키", status=None, limit=20))
    sql = [
        str(statement.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))
        for statement in statements
    ]
    assert len(sql) == 3
    assert "passports.user_id = 7" in sql[0] and "stamp_submissions" in sql[0]
    assert "collected_stamps" in sql[1] and "saved_activities" in sql[2]
    assert all("스키" in statement and "LIMIT 20" in statement for statement in sql)


def test_saved_activity_and_reward_conflicts_are_explicit():
    class Repository:
        activity = SimpleNamespace(id=9)
        saved = None
        count = 5

        async def activity_exists(self, _activity_id):
            return self.activity is not None

        async def saved_activity(self, _user_id, _activity_id):
            return self.saved

        async def save_activity(self, user_id, activity_id):
            row = SimpleNamespace(id=1, activity_id=activity_id, created_at=NOW)
            return row, self.activity

        async def badge_count(self, _user_id):
            return self.count

        async def reward_claim(self, _user_id, _milestone):
            return self.saved

        async def create_reward_claim(self, user_id, milestone, body):
            return SimpleNamespace(
                id=1,
                user_id=user_id,
                milestone=milestone,
                recipient_name=body.recipient_name,
                phone_number=body.phone_number,
                address=body.address,
                status=RewardClaimStatus.requested,
                requested_at=NOW,
                fulfilled_at=None,
            )

    repository = Repository()
    service = MeService(repository, Storage())
    user = LoginUser(7, "u@example.com")
    assert run(service.save_activity(9, user))["activity_id"] == 9
    repository.saved = SimpleNamespace(id=1)
    with pytest.raises(ApiError) as error:
        run(service.save_activity(9, user))
    assert error.value.status == 409

    repository.saved = None
    body = SimpleNamespace(recipient_name="홍길동", phone_number="01012345678", address="강원")
    with pytest.raises(ApiError) as error:
        run(service.claim_reward(RewardMilestone.badge_6, body, user))
    assert error.value.status == 409 and error.value.code == "not_eligible"
    repository.count = 6
    assert run(service.claim_reward(RewardMilestone.badge_6, body, user)).status == "requested"


def test_user_feature_models_and_mission_fields_are_in_metadata():
    assert {"saved_activities", "reward_claims"} <= set(Base.metadata.tables)
    assert any(
        constraint.name == "badges_rule_key_unique"
        for constraint in Base.metadata.tables["badges"].constraints
    )
    assert {
        "participation_period",
        "proof_instructions",
        "photo_prompt",
        "reward_description",
        "steps",
        "official_url",
        "official_label",
    } <= set(Base.metadata.tables["courses"].c.keys())


def test_me_and_reward_routes_require_login_and_preserve_contract(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "user-feature-route-secret")
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    token = sign_access_token(LoginUser(7, "user@example.com"))[0]
    headers = {"Authorization": f"Bearer {token}"}
    admin_token = sign_access_token(LoginUser(8, "admin@example.com"))[0]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    activity = {
        "id": 9,
        "category": "sports",
        "representative_image_url": None,
        "sport_name": "ski",
        "region": "강원",
        "sigun": "평창군",
        "place_name": "스키장",
        "latitude": None,
        "longitude": None,
        "created_at": NOW,
        "updated_at": NOW,
    }

    class Service:
        async def badges(self, actor, *, offset, limit):
            assert (actor.id, offset, limit) == (7, 0, 20)
            return []

        async def saved_activities(self, actor, *, offset, limit):
            return []

        async def save_activity(self, activity_id, actor):
            assert (activity_id, actor.id) == (9, 7)
            return {"id": 1, "activity_id": 9, "created_at": NOW, "activity": activity}

        async def activity_history(self, actor, **filters):
            assert filters["q"] == "스키" and filters["status"] == "approved"
            return []

        async def rewards(self, actor, *, offset, limit):
            return []

        async def claim_reward(self, milestone, body, actor):
            assert milestone == RewardMilestone.badge_6 and actor.id == 7
            return {
                "id": 1,
                "user_id": 7,
                "milestone": milestone,
                "recipient_name": body.recipient_name,
                "phone_number": body.phone_number,
                "address": body.address,
                "status": RewardClaimStatus.requested,
                "requested_at": NOW,
                "fulfilled_at": None,
            }

        async def admin_reward_claims(self, claim_status, *, offset, limit):
            assert claim_status == RewardClaimStatus.requested
            assert (offset, limit) == (0, 20)
            return []

        async def update_reward_claim(self, claim_id, body):
            assert claim_id == 1 and body.status == RewardClaimStatus.shipped
            return {
                "id": 1,
                "user_id": 7,
                "milestone": RewardMilestone.badge_6,
                "recipient_name": "홍길동",
                "phone_number": "010-1234-5678",
                "address": "강원특별자치도",
                "status": body.status,
                "requested_at": NOW,
                "fulfilled_at": None,
            }

    app.dependency_overrides[get_me_service] = Service
    try:
        with TestClient(app) as client:
            assert client.get("/api/me/badges").status_code == 401
            assert client.get("/api/me/badges", headers=headers).status_code == 200
            saved = client.post("/api/me/saved-activities/9", headers=headers)
            history = client.get(
                "/api/me/activity-history?q=스키&status=approved", headers=headers
            )
            claim = client.post(
                "/api/me/rewards/badge_6/claim",
                headers=headers,
                json={
                    "recipientName": "홍길동",
                    "phoneNumber": "010-1234-5678",
                    "address": "강원특별자치도",
                },
            )
            admin_list = client.get(
                "/api/admin/reward-claims?status=requested", headers=admin_headers
            )
            shipped = client.patch(
                "/api/admin/reward-claims/1",
                headers=admin_headers,
                json={"status": "shipped"},
            )
        assert saved.json()["activityId"] == 9
        assert history.status_code == 200
        assert claim.status_code == 201 and claim.json()["status"] == "requested"
        assert admin_list.status_code == 200 and shipped.json()["status"] == "shipped"
    finally:
        app.dependency_overrides.clear()
