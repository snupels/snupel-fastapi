import asyncio
from datetime import datetime

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from app.deps.auth import LoginUser, require_user
from app.exceptions import ApiError
from app.main import app
from app.models import Base, PassportRewardCampaign, PassportTeeClaim, TeeClaimStatus
from app.repositories.passport_reward import CAMPAIGN_ID, PassportRewardRepository
from app.schemas.passport_reward import TeeClaimCreate, TeeClaimPatch, TeeRewardResponse
from app.services.passport_reward import PassportRewardService, get_passport_reward_service

FORM = dict(
    size="M",
    recipientName="테스트 회원",
    phoneNumber="010-1234-5678",
    postalCode="24300",
    address="강원특별자치도 춘천시 테스트길 1",
    addressDetail="101호",
    shippingConsent=True,
)
ACTOR = LoginUser(1, "member@example.invalid")
run = asyncio.run


@pytest.fixture
def repository():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        for sql in (
            "CREATE TABLE users (id INTEGER PRIMARY KEY)",
            "CREATE TABLE passports (id INTEGER PRIMARY KEY, user_id INTEGER)",
            "CREATE TABLE stamps (id INTEGER PRIMARY KEY, stamp_catalog_id INTEGER)",
            "CREATE TABLE collected_stamps (id INTEGER PRIMARY KEY, passport_id INTEGER, stamp_id INTEGER)",
            "INSERT INTO users VALUES (1), (2)",
            "INSERT INTO passports VALUES (1, 1), (2, 2)",
            "INSERT INTO stamps VALUES (1,1),(2,2),(3,3),(4,4),(5,5),(6,5)",
            "INSERT INTO collected_stamps VALUES (1,1,1),(2,1,2),(3,1,3),(4,1,4),(5,1,5),(6,1,6)",
        ):
            connection.execute(sa.text(sql))
    metadata = sa.MetaData()
    # Reference-only tables allow normal foreign key resolution without unrelated schema.
    sa.Table("users", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    for model in (PassportRewardCampaign, PassportTeeClaim):
        table = model.__table__.to_metadata(metadata)
        if model == PassportTeeClaim:
            table.c.id.type = sa.Integer()
    metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:

        class Adapter:
            add = session.add

            async def scalar(self, query):
                return session.scalar(query)

            async def scalars(self, query):
                return session.scalars(query)

            async def flush(self):
                session.flush()

            async def refresh(self, row):
                session.refresh(row)

            async def commit(self):
                session.commit()

            async def rollback(self):
                session.rollback()

        session.add(
            PassportRewardCampaign(
                id=CAMPAIGN_ID, required_stamps=5, quantity=100, claimed_count=0, is_open=True
            )
        )
        session.commit()
        yield PassportRewardRepository(Adapter()), session
    engine.dispose()


@pytest.mark.parametrize(
    "change",
    [
        {"shippingConsent": False},
        {"shippingConsent": 1},
        {"size": "XXXL"},
        {"postalCode": "1234"},
        {"phoneNumber": "123456789"},
        {"recipientName": " "},
        {"address": "x"},
        {"userId": 2},
    ],
)
def test_invalid_claim_input_is_rejected(change):
    with pytest.raises(ValidationError):
        TeeClaimCreate(**(FORM | change))


def test_real_claims_count_distinct_collected_stamps_commit_once_and_preserve_awards(repository):
    repo, session = repository
    service = PassportRewardService(repo)
    status = run(service.status(ACTOR))
    assert status["eligible"] and status["collected_stamps"] == 5
    assert TeeRewardResponse.model_validate(status)
    first = run(service.claim(TeeClaimCreate(**FORM), ACTOR))
    assert first.allocation_no == 1 and first.phone_number == "01012345678"
    assert first.status == TeeClaimStatus.requested and first.consent_version
    assert first.requested_at and first.consented_at
    retry = run(service.claim(TeeClaimCreate(**(FORM | {"size": "L"})), ACTOR))
    assert retry.id == first.id and retry.size == "M", (
        "Retries must not silently rewrite existing applications"
    )
    assert session.scalar(sa.select(sa.func.count(PassportTeeClaim.id))) == 1
    assert run(repo.campaign()).claimed_count == 1
    assert session.scalar(sa.text("SELECT count(*) FROM collected_stamps")) == 6
    assert run(service.status(ACTOR))["claim"].id == first.id
    assert run(service.status(LoginUser(2, "other@example.invalid")))["claim"] is None


def test_unqualified_full_closed_and_last_slot_enforced(repository):
    repo, session = repository
    service = PassportRewardService(repo)
    with pytest.raises(ApiError) as failure:
        run(service.claim(TeeClaimCreate(**FORM), LoginUser(2, "other@example.invalid")))
    assert failure.value.code == "not_eligible"
    campaign = run(repo.campaign())
    campaign.is_open = False
    session.commit()
    with pytest.raises(ApiError) as failure:
        run(service.claim(TeeClaimCreate(**FORM), ACTOR))
    assert failure.value.status == 409
    campaign.is_open = True
    campaign.claimed_count = 99
    session.commit()
    assert run(service.claim(TeeClaimCreate(**FORM), ACTOR)).allocation_no == 100
    assert run(service.status(ACTOR))["remaining"] == 0
    session.execute(
        sa.text("INSERT INTO collected_stamps VALUES (7,2,1),(8,2,2),(9,2,3),(10,2,4),(11,2,5)")
    )
    session.commit()
    with pytest.raises(ApiError) as failure:
        run(service.claim(TeeClaimCreate(**FORM), LoginUser(2, "other@example.invalid")))
    assert failure.value.code == "sold_out"
    assert run(repo.campaign()).claimed_count == 100


def test_failed_transaction_does_not_consume_a_slot(repository, monkeypatch):
    repo, session = repository
    original = repo.create

    async def fail(*args):
        await original(*args)
        raise sa.exc.IntegrityError("synthetic test", {}, Exception("test"))

    monkeypatch.setattr(repo, "create", fail)
    with pytest.raises(ApiError):
        run(PassportRewardService(repo).claim(TeeClaimCreate(**FORM), ACTOR))
    assert run(repo.campaign()).claimed_count == 0
    assert session.scalar(sa.select(sa.func.count(PassportTeeClaim.id))) == 0


def test_fulfillment_is_separate_and_cannot_move_backwards(repository):
    repo, _ = repository
    service = PassportRewardService(repo)
    claim = run(service.claim(TeeClaimCreate(**FORM), ACTOR))
    result = run(service.update(claim.id, TeeClaimPatch(status="completed")))
    assert result.fulfilled_at and result.status == TeeClaimStatus.completed
    completed_at = result.fulfilled_at
    assert (
        run(service.update(claim.id, TeeClaimPatch(status="completed"))).fulfilled_at
        == completed_at
    )
    with pytest.raises(ApiError):
        run(service.update(claim.id, TeeClaimPatch(status="requested")))
    with pytest.raises(ApiError) as failure:
        run(service.update(999, TeeClaimPatch(status="shipped")))
    assert failure.value.status == 404


def test_mysql_queries_use_consistent_campaign_and_member_locks_and_scoped_owner():
    sql = []

    class Session:
        async def scalar(self, query):
            sql.append(
                str(query.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))
            )
            return None

    repo = PassportRewardRepository(Session())
    run(repo.campaign(lock=True))
    run(repo.own_claim(12, lock=True))
    run(repo.stamp_count(12))
    assert sql[0].endswith("FOR UPDATE") and sql[1].endswith("FOR UPDATE")
    assert "user_id = 12" in sql[1] and "distinct(stamps.stamp_catalog_id)" in sql[2]
    assert "passports.user_id = 12" in sql[2]
    constraints = {c.name for c in Base.metadata.tables["passport_tee_claims"].constraints}
    assert {"tee_claim_member_unique", "tee_claim_slot_unique"} <= constraints


def test_routes_auth_ownership_errors_privacy_and_admin_permissions(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.invalid")
    row = dict(
        id=1,
        allocation_no=1,
        size="M",
        recipient_name="테스트",
        phone_number="01012345678",
        postal_code="24300",
        address="테스트 주소",
        address_detail="",
        status="requested",
        requested_at=datetime(2026, 10, 15),
        fulfilled_at=None,
    )

    class Service:
        async def status(self, actor):
            return dict(
                required_stamps=5,
                collected_stamps=5,
                quantity=100,
                remaining=99,
                is_open=True,
                eligible=True,
                can_manage=False,
                claim=row if actor.id == 1 else None,
            )

        async def claim(self, body, actor):
            if body.size == "S":
                raise ApiError(409, "sold_out", "Sold out")
            return row

        async def admin_claims(self, **_):
            return [row]

        async def update(self, *_):
            return row

    app.dependency_overrides[get_passport_reward_service] = Service
    try:
        with TestClient(app) as client:
            assert client.get("/api/me/passport-rewards/tee").status_code == 401
            assert client.post("/api/me/passport-rewards/tee/claim", json=FORM).status_code == 401
            app.dependency_overrides[require_user] = lambda: ACTOR
            response = client.get("/api/me/passport-rewards/tee")
            assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
            assert response.json()["claim"]["recipientName"] == "테스트"
            assert client.post("/api/me/passport-rewards/tee/claim", json=FORM).status_code == 201
            assert (
                client.post(
                    "/api/me/passport-rewards/tee/claim", json=FORM | {"shippingConsent": False}
                ).status_code
                == 400
            )
            assert (
                client.post("/api/me/passport-rewards/tee/claim", json=FORM | {"size": "S"}).json()[
                    "error"
                ]
                == "sold_out"
            )
            assert client.get("/api/admin/passport-tee-claims").status_code == 403
            assert (
                client.patch(
                    "/api/admin/passport-tee-claims/1", json={"status": "shipped"}
                ).status_code
                == 403
            )
            app.dependency_overrides[require_user] = lambda: LoginUser(2, "other@example.invalid")
            assert client.get("/api/me/passport-rewards/tee").json()["claim"] is None
            app.dependency_overrides[require_user] = lambda: LoginUser(3, "admin@example.invalid")
            assert client.get("/api/admin/passport-tee-claims").status_code == 200
            assert (
                client.patch(
                    "/api/admin/passport-tee-claims/1", json={"status": "shipped"}
                ).status_code
                == 200
            )
    finally:
        app.dependency_overrides.pop(get_passport_reward_service, None)
        app.dependency_overrides.pop(require_user, None)
