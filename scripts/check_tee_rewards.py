"""Read-only production check: aggregate allocation state only, never member data."""

import asyncio
import json

import httpx
from sqlalchemy import func, select

from app.config.database import SessionLocal, engine
from app.models import PassportTeeClaim
from app.repositories.passport_reward import PassportRewardRepository


async def main():
    try:
        async with SessionLocal() as session:
            campaign = await PassportRewardRepository(session).campaign()
            assert campaign and campaign.required_stamps == 5 and campaign.quantity == 100
            assert campaign.is_open and 0 <= campaign.claimed_count <= 100
            rows = int(await session.scalar(select(func.count(PassportTeeClaim.id))) or 0)
            assert rows <= campaign.claimed_count
            metadata = dict(
                requiredStamps=campaign.required_stamps,
                quantity=campaign.quantity,
                allocated=campaign.claimed_count,
                remaining=campaign.quantity - campaign.claimed_count,
                isOpen=campaign.is_open,
            )
            await session.rollback()
        async with httpx.AsyncClient(timeout=15) as client:
            for path in ("me/passport-rewards/tee", "admin/passport-tee-claims"):
                response = await client.get("https://api.sportspassport.kr/api/" + path)
                assert (
                    response.status_code == 401
                    and response.headers.get("cache-control") == "no-store"
                )
        print(
            json.dumps(
                {"teeReward": metadata, "authenticationRequired": True, "wroteApplications": False}
            )
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
