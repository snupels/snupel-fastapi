from fastapi import Depends
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.deps.auth import is_admin
from app.exceptions import ApiError
from app.models import TeeClaimStatus
from app.repositories.passport_reward import PassportRewardRepository


class PassportRewardService:
    def __init__(self, repository):
        self.repository = repository

    async def status(self, actor):
        campaign = await self.repository.campaign()
        if campaign is None:
            raise ApiError(503, "reward_unavailable", "Reward is not configured.")
        count = await self.repository.stamp_count(actor.id)
        claim = await self.repository.own_claim(actor.id)
        remaining = max(0, campaign.quantity - campaign.claimed_count)
        return dict(
            required_stamps=campaign.required_stamps,
            collected_stamps=count,
            quantity=campaign.quantity,
            remaining=remaining,
            is_open=campaign.is_open,
            eligible=claim is None
            and campaign.is_open
            and remaining > 0
            and count >= campaign.required_stamps,
            can_manage=is_admin(actor),
            claim=claim,
        )

    async def claim(self, body, actor):
        # One campaign row serializes allocation across all workers/instances.
        # Always acquire locks in campaign -> member-claim order.
        campaign = await self.repository.campaign(lock=True)
        if campaign is None:
            raise ApiError(503, "reward_unavailable", "Reward is not configured.")
        existing = await self.repository.own_claim(actor.id, lock=True)
        if existing is not None:
            return existing  # Idempotent retry after a lost response: never use another slot.
        if not campaign.is_open:
            raise ApiError(409, "reward_closed", "Applications are closed.")
        if await self.repository.stamp_count(actor.id) < campaign.required_stamps:
            raise ApiError(409, "not_eligible", "Five collected stamps are required.")
        if campaign.claimed_count >= campaign.quantity:
            raise ApiError(409, "sold_out", "All reward places have been allocated.")
        try:
            row = await self.repository.create(campaign, actor.id, body)
            await self.repository.commit()  # Persist before reporting success to the browser.
            return row
        except IntegrityError as error:
            await self.repository.rollback()
            existing = await self.repository.own_claim(actor.id)
            if existing is not None:
                return existing
            raise ApiError(
                409, "claim_conflict", "Please refresh the reward status and retry."
            ) from error
        except SQLAlchemyError:
            await self.repository.rollback()
            raise ApiError(
                503,
                "reward_unavailable",
                "Unable to confirm the application. Refresh your claim status before retrying.",
            ) from None

    async def admin_claims(self, *, offset, limit):
        return await self.repository.admin_claims(offset=offset, limit=limit)

    async def update(self, claim_id, body):
        row = await self.repository.get_claim(claim_id)
        if row is None:
            raise ApiError(404, "not_found", "Claim not found.")
        order = list(TeeClaimStatus)
        if order.index(body.status) < order.index(row.status):
            raise ApiError(409, "invalid_transition", "Fulfillment status cannot move backwards.")
        return await self.repository.update(row, body.status)


def get_passport_reward_service(session: AsyncSession = Depends(get_session)):
    return PassportRewardService(PassportRewardRepository(session))
