from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CollectedStamp,
    Passport,
    PassportRewardCampaign,
    PassportTeeClaim,
    Stamp,
    TeeClaimStatus,
)

CAMPAIGN_ID = "gsp-tee-2026"
CONSENT_VERSION = "tee-shipping-2026-10-15"


class PassportRewardRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def campaign(self, *, lock=False):
        query = select(PassportRewardCampaign).where(PassportRewardCampaign.id == CAMPAIGN_ID)
        return await self.session.scalar(query.with_for_update() if lock else query)

    async def own_claim(self, user_id, *, lock=False):
        query = select(PassportTeeClaim).where(
            PassportTeeClaim.campaign_id == CAMPAIGN_ID, PassportTeeClaim.user_id == user_id
        )
        return await self.session.scalar(query.with_for_update() if lock else query)

    async def stamp_count(self, user_id):
        # Count the same collected stamp identities used by the member stampbook.
        return int(
            await self.session.scalar(
                select(func.count(func.distinct(Stamp.stamp_catalog_id)))
                .select_from(CollectedStamp)
                .join(Passport, Passport.id == CollectedStamp.passport_id)
                .join(Stamp, Stamp.id == CollectedStamp.stamp_id)
                .where(Passport.user_id == user_id)
            )
            or 0
        )

    async def create(self, campaign, user_id, body):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        campaign.claimed_count += 1
        row = PassportTeeClaim(
            campaign_id=campaign.id,
            user_id=user_id,
            allocation_no=campaign.claimed_count,
            **body.model_dump(exclude={"shipping_consent"}),
            consent_version=CONSENT_VERSION,
            status=TeeClaimStatus.requested,
            requested_at=now,
            consented_at=now,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()

    async def admin_claims(self, *, offset, limit):
        return list(
            await self.session.scalars(
                select(PassportTeeClaim)
                .where(
                    PassportTeeClaim.campaign_id == CAMPAIGN_ID,
                )
                .order_by(PassportTeeClaim.allocation_no)
                .offset(offset)
                .limit(limit)
            )
        )

    async def get_claim(self, claim_id):
        return await self.session.scalar(
            select(PassportTeeClaim)
            .where(
                PassportTeeClaim.id == claim_id,
                PassportTeeClaim.campaign_id == CAMPAIGN_ID,
            )
            .with_for_update()
        )

    async def update(self, row, status):
        row.status = status
        if status == TeeClaimStatus.completed and row.fulfilled_at is None:
            row.fulfilled_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.session.flush()
        await self.commit()
        return row
