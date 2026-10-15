"""Real MySQL locking checks. Runs only against the disposable CI test database."""

import asyncio
import importlib.util
import os

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.deps.auth import LoginUser
from app.exceptions import ApiError
from app.repositories.passport_reward import PassportRewardRepository
from app.schemas.passport_reward import TeeClaimCreate
from app.services.passport_reward import PassportRewardService

URL = os.getenv("TEE_TEST_MYSQL_URL")


@pytest.mark.skipif(not URL, reason="Disposable MySQL integration database not configured")
def test_mysql_last_slot_race_and_same_member_retries_are_atomic():
    assert make_url(URL).database == "tee_reward_tests", (
        "Never run fixture cleanup against production"
    )

    async def scenario():
        engine = create_async_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async def cleanup(connection):
            for name in ("passport_tee_claims", "passport_reward_campaigns", "users"):
                await connection.execute(text(f"DROP TABLE IF EXISTS {name}"))

        try:
            async with engine.begin() as connection:
                await cleanup(connection)
                await connection.execute(
                    text("CREATE TABLE users (id BIGINT UNSIGNED PRIMARY KEY)")
                )
                await connection.execute(
                    text("INSERT INTO users (id) VALUES (:id)"), [{"id": i} for i in range(1, 13)]
                )
                spec = importlib.util.spec_from_file_location(
                    "tee_migration", "alembic/versions/0052_passport_tee_rewards.py"
                )
                migration = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(migration)

                def upgrade(sync_connection):
                    with Operations.context(MigrationContext.configure(sync_connection)):
                        migration.upgrade()

                await connection.run_sync(upgrade)
                await connection.execute(
                    text("UPDATE passport_reward_campaigns SET claimed_count=99")
                )

            class QualifiedRepository(PassportRewardRepository):
                async def stamp_count(self, _user_id):
                    return 5

            async def apply(user_id):
                async with sessions() as session:
                    try:
                        row = await PassportRewardService(QualifiedRepository(session)).claim(
                            TeeClaimCreate(
                                size="M",
                                recipientName="CI test",
                                phoneNumber="01012345678",
                                postalCode="24300",
                                address="CI shipping fixture",
                                shippingConsent=True,
                            ),
                            LoginUser(user_id, f"test-{user_id}@example.invalid"),
                        )
                        return row.id, row.allocation_no
                    except ApiError as error:
                        await session.rollback()
                        return error.code

            results = await asyncio.gather(*(apply(i) for i in range(1, 13)))
            assert sum(isinstance(result, tuple) for result in results) == 1
            assert results.count("sold_out") == 11
            async with engine.begin() as connection:
                assert (
                    await connection.scalar(
                        text("SELECT claimed_count FROM passport_reward_campaigns")
                    )
                    == 100
                )
                assert (
                    await connection.scalar(text("SELECT count(*) FROM passport_tee_claims")) == 1
                )
                await connection.execute(text("DELETE FROM passport_tee_claims"))
                await connection.execute(
                    text("UPDATE passport_reward_campaigns SET claimed_count=0")
                )
            retries = await asyncio.gather(*(apply(1) for _ in range(10)))
            assert len(set(retries)) == 1 and retries[0][1] == 1
            async with engine.begin() as connection:
                assert (
                    await connection.scalar(
                        text("SELECT claimed_count FROM passport_reward_campaigns")
                    )
                    == 1
                )
                assert (
                    await connection.scalar(text("SELECT count(*) FROM passport_tee_claims")) == 1
                )
        finally:
            async with engine.begin() as connection:
                await cleanup(connection)
            await engine.dispose()

    asyncio.run(scenario())
