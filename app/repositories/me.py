from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Activity,
    Badge,
    CollectedBadge,
    CollectedStamp,
    Course,
    CourseStamp,
    Passport,
    RewardClaim,
    RewardClaimStatus,
    RewardMilestone,
    SavedActivity,
    Stamp,
    StampSubmission,
)


class MeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def badges(self, user_id: int, *, offset: int, limit: int):
        return (
            await self.session.execute(
                select(
                    CollectedBadge.id,
                    Badge.id.label("badge_id"),
                    Badge.rule_key,
                    Badge.image_url,
                    Badge.description,
                    CollectedBadge.collected_at,
                )
                .join(Passport, Passport.id == CollectedBadge.passport_id)
                .join(Badge, Badge.id == CollectedBadge.badge_id)
                .where(Passport.user_id == user_id)
                .order_by(CollectedBadge.collected_at.desc(), CollectedBadge.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).mappings().all()

    async def saved_activities(self, user_id: int, *, offset: int, limit: int):
        return (
            await self.session.execute(
                select(SavedActivity, Activity)
                .join(Activity, Activity.id == SavedActivity.activity_id)
                .where(SavedActivity.user_id == user_id)
                .order_by(SavedActivity.created_at.desc(), SavedActivity.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()

    async def activity_exists(self, activity_id: int) -> bool:
        return await self.session.get(Activity, activity_id) is not None

    async def saved_activity(self, user_id: int, activity_id: int):
        return await self.session.scalar(
            select(SavedActivity).where(
                SavedActivity.user_id == user_id,
                SavedActivity.activity_id == activity_id,
            )
        )

    async def save_activity(self, user_id: int, activity_id: int):
        row = SavedActivity(user_id=user_id, activity_id=activity_id)
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        activity = await self.session.get(Activity, activity_id)
        return row, activity

    async def remove_saved_activity(self, row: SavedActivity) -> None:
        await self.session.delete(row)
        await self.session.flush()

    @staticmethod
    def _course(stamp_id):
        course_id = (
            select(Course.id)
            .join(CourseStamp, CourseStamp.course_id == Course.id)
            .where(CourseStamp.stamp_id == stamp_id, Course.is_published.is_(True))
            .order_by(Course.id)
            .limit(1)
            .scalar_subquery()
        )
        course_title = (
            select(Course.title)
            .join(CourseStamp, CourseStamp.course_id == Course.id)
            .where(CourseStamp.stamp_id == stamp_id, Course.is_published.is_(True))
            .order_by(Course.id)
            .limit(1)
            .scalar_subquery()
        )
        return course_id, course_title

    @staticmethod
    def _search(query, q: str | None, title):
        if not q:
            return query
        return query.where(
            or_(
                title.contains(q),
                Activity.place_name.contains(q),
                Activity.sigun.contains(q),
                Activity.sport_name.contains(q),
                Activity.summary.contains(q),
                Activity.address.contains(q),
            )
        )

    def _submission_history(self, user_id: int, q: str | None, status: str | None):
        course_id, course_title = self._course(Stamp.id)
        title = func.coalesce(course_title, Activity.place_name, Stamp.description)
        query = (
            select(
                StampSubmission.id.label("source_id"),
                StampSubmission.status,
                Activity.id.label("activity_id"),
                course_id.label("course_id"),
                StampSubmission.id.label("submission_id"),
                title.label("title"),
                Activity.place_name,
                Activity.sigun,
                StampSubmission.object_key,
                StampSubmission.created_at.label("occurred_at"),
                StampSubmission.rejection_reason,
            )
            .join(Passport, Passport.id == StampSubmission.passport_id)
            .join(Stamp, Stamp.id == StampSubmission.stamp_id)
            .join(Activity, Activity.id == Stamp.activity_id)
            .where(Passport.user_id == user_id)
        )
        if status and status != "collected":
            query = query.where(StampSubmission.status == status)
        elif status == "collected":
            query = query.where(False)
        return self._search(query, q, title)

    def _stamp_history(self, user_id: int, q: str | None, status: str | None):
        course_id, course_title = self._course(Stamp.id)
        title = func.coalesce(course_title, Activity.place_name, Stamp.description)
        query = (
            select(
                CollectedStamp.id.label("source_id"),
                Activity.id.label("activity_id"),
                course_id.label("course_id"),
                title.label("title"),
                Activity.place_name,
                Activity.sigun,
                Activity.representative_image_url.label("image_url"),
                CollectedStamp.collected_at.label("occurred_at"),
            )
            .join(Passport, Passport.id == CollectedStamp.passport_id)
            .join(Stamp, Stamp.id == CollectedStamp.stamp_id)
            .join(Activity, Activity.id == Stamp.activity_id)
            .where(Passport.user_id == user_id)
        )
        if status and status != "collected":
            query = query.where(False)
        return self._search(query, q, title)

    def _saved_history(self, user_id: int, q: str | None, status: str | None):
        stamp_id = (
            select(func.min(Stamp.id))
            .where(Stamp.activity_id == Activity.id)
            .correlate(Activity)
            .scalar_subquery()
        )
        course_id, course_title = self._course(stamp_id)
        title = func.coalesce(course_title, Activity.place_name)
        query = (
            select(
                SavedActivity.id.label("source_id"),
                Activity.id.label("activity_id"),
                course_id.label("course_id"),
                title.label("title"),
                Activity.place_name,
                Activity.sigun,
                Activity.representative_image_url.label("image_url"),
                SavedActivity.created_at.label("occurred_at"),
            )
            .join(Activity, Activity.id == SavedActivity.activity_id)
            .where(SavedActivity.user_id == user_id)
        )
        if status and status != "collected":
            query = query.where(False)
        return self._search(query, q, title)

    async def activity_history(
        self, user_id: int, *, q: str | None, status: str | None, limit: int
    ):
        queries = (
            self._submission_history(user_id, q, status),
            self._stamp_history(user_id, q, status),
            self._saved_history(user_id, q, status),
        )
        return [
            (
                await self.session.execute(
                    query.order_by(query.selected_columns.occurred_at.desc()).limit(limit)
                )
            ).mappings().all()
            for query in queries
        ]

    async def activity_history_item(self, user_id: int, kind: str, source_id: int):
        query = {
            "submission": self._submission_history,
            "stamp": self._stamp_history,
            "saved": self._saved_history,
        }[kind](user_id, None, None).where(
            {
                "submission": StampSubmission.id,
                "stamp": CollectedStamp.id,
                "saved": SavedActivity.id,
            }[kind]
            == source_id
        )
        return (await self.session.execute(query)).mappings().first()

    async def badge_count(self, user_id: int) -> int:
        return int(
            await self.session.scalar(
                select(func.count(CollectedBadge.id))
                .join(Passport, Passport.id == CollectedBadge.passport_id)
                .where(Passport.user_id == user_id)
            )
            or 0
        )

    async def reward_claims(self, user_id: int):
        return list(
            await self.session.scalars(
                select(RewardClaim)
                .where(RewardClaim.user_id == user_id)
                .order_by(RewardClaim.id)
            )
        )

    async def reward_claim(self, user_id: int, milestone: RewardMilestone):
        return await self.session.scalar(
            select(RewardClaim).where(
                RewardClaim.user_id == user_id,
                RewardClaim.milestone == milestone,
            )
        )

    async def create_reward_claim(self, user_id: int, milestone: RewardMilestone, body):
        row = RewardClaim(
            user_id=user_id,
            milestone=milestone,
            recipient_name=body.recipient_name,
            phone_number=body.phone_number,
            address=body.address,
            status=RewardClaimStatus.requested,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def admin_reward_claims(
        self, status: RewardClaimStatus | None, *, offset: int, limit: int
    ):
        query = select(RewardClaim)
        if status:
            query = query.where(RewardClaim.status == status)
        return list(
            await self.session.scalars(
                query.order_by(RewardClaim.requested_at, RewardClaim.id)
                .offset(offset)
                .limit(limit)
            )
        )

    async def get_reward_claim(self, claim_id: int):
        return await self.session.scalar(
            select(RewardClaim).where(RewardClaim.id == claim_id).with_for_update()
        )

    async def update_reward_claim(self, row: RewardClaim, status: RewardClaimStatus):
        row.status = status
        if status == RewardClaimStatus.completed and row.fulfilled_at is None:
            row.fulfilled_at = datetime.now()
        elif status != RewardClaimStatus.completed:
            row.fulfilled_at = None
        await self.session.flush()
        await self.session.refresh(row)
        return row
