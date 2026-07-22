from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CollectedStamp,
    Course,
    CourseStamp,
    Passport,
    StampSubmission,
    SubmissionStatus,
)


class StampSubmissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def valid_target(self, passport_id: int, stamp_id: int, user_id: int) -> bool:
        return bool(
            await self.session.scalar(
                select(
                    exists().where(
                        Passport.id == passport_id,
                        Passport.user_id == user_id,
                        CourseStamp.stamp_id == stamp_id,
                        Course.id == CourseStamp.course_id,
                        Course.is_published.is_(True),
                    )
                )
            )
        )

    async def pending(self, passport_id: int, stamp_id: int) -> bool:
        return bool(
            await self.session.scalar(
                select(
                    exists().where(
                        StampSubmission.passport_id == passport_id,
                        StampSubmission.stamp_id == stamp_id,
                        StampSubmission.status == SubmissionStatus.pending,
                    )
                )
            )
        )

    async def collected(self, passport_id: int, stamp_id: int) -> bool:
        return bool(
            await self.session.scalar(
                select(
                    exists().where(
                        CollectedStamp.passport_id == passport_id,
                        CollectedStamp.stamp_id == stamp_id,
                    )
                )
            )
        )

    async def create(self, passport_id: int, stamp_id: int, object_key: str):
        row = StampSubmission(
            passport_id=passport_id,
            stamp_id=stamp_id,
            object_key=object_key,
            status=SubmissionStatus.pending,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def list_user(self, user_id: int):
        return list(
            await self.session.scalars(
                select(StampSubmission)
                .join(Passport, Passport.id == StampSubmission.passport_id)
                .where(Passport.user_id == user_id)
                .order_by(StampSubmission.id.desc())
            )
        )

    async def list_status(self, status: SubmissionStatus):
        return list(
            await self.session.scalars(
                select(StampSubmission)
                .where(StampSubmission.status == status)
                .order_by(StampSubmission.id)
            )
        )

    async def get(self, item_id: int):
        return await self.session.scalar(
            select(StampSubmission).where(StampSubmission.id == item_id).with_for_update()
        )

    async def approve(self, row: StampSubmission, reviewer_id: int):
        if not await self.collected(row.passport_id, row.stamp_id):
            self.session.add(
                CollectedStamp(passport_id=row.passport_id, stamp_id=row.stamp_id)
            )
        row.status = SubmissionStatus.approved
        row.reviewer_id = reviewer_id
        row.reviewed_at = datetime.now()
        row.rejection_reason = None
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def reject(self, row: StampSubmission, reviewer_id: int, reason: str):
        row.status = SubmissionStatus.rejected
        row.reviewer_id = reviewer_id
        row.reviewed_at = datetime.now()
        row.rejection_reason = reason
        await self.session.flush()
        await self.session.refresh(row)
        return row
