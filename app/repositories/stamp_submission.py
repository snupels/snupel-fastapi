from datetime import datetime

from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Activity,
    CollectedStamp,
    Course,
    CourseStamp,
    FeedComment,
    FeedLike,
    Passport,
    Stamp,
    StampSubmission,
    SubmissionStatus,
    User,
)


class StampSubmissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def valid_target(
        self, passport_id: int, stamp_id: int, user_id: int, *, lock: bool = False
    ) -> bool:
        passport = select(Passport.id).where(
            Passport.id == passport_id, Passport.user_id == user_id
        )
        if lock:
            passport = passport.with_for_update()
        if await self.session.scalar(passport) is None:
            return False
        return bool(
            await self.session.scalar(
                select(
                    exists().where(
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

    async def create(
        self,
        passport_id: int,
        stamp_id: int,
        object_key: str,
        *,
        share_to_feed: bool = False,
        feed_caption: str | None = None,
    ):
        row = StampSubmission(
            passport_id=passport_id,
            stamp_id=stamp_id,
            object_key=object_key,
            share_to_feed=share_to_feed,
            feed_caption=feed_caption,
            status=SubmissionStatus.pending,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def list_user(self, user_id: int, *, offset: int = 0, limit: int = 20):
        return list(
            await self.session.scalars(
                select(StampSubmission)
                .join(Passport, Passport.id == StampSubmission.passport_id)
                .where(Passport.user_id == user_id)
                .order_by(StampSubmission.id.desc())
                .offset(offset)
                .limit(limit)
            )
        )

    async def list_status(
        self, status: SubmissionStatus, *, offset: int = 0, limit: int = 20
    ):
        query = (
            select(StampSubmission, Activity)
            .join(Stamp, Stamp.id == StampSubmission.stamp_id)
            .join(Activity, Activity.id == Stamp.activity_id)
            .where(StampSubmission.status == status)
            .order_by(StampSubmission.id)
            .offset(offset)
            .limit(limit)
        )
        return list(
            (await self.session.execute(query)).all()
        )

    async def get(self, item_id: int):
        return await self.session.scalar(
            select(StampSubmission).where(StampSubmission.id == item_id).with_for_update()
        )

    async def get_owned(self, item_id: int, user_id: int):
        return await self.session.scalar(
            select(StampSubmission)
            .join(Passport, Passport.id == StampSubmission.passport_id)
            .where(StampSubmission.id == item_id, Passport.user_id == user_id)
            .with_for_update()
        )

    async def list_feed(
        self,
        *,
        user_id: int | None = None,
        offset: int = 0,
        limit: int = 20,
    ):
        query = (
            select(StampSubmission, Activity, User)
            .join(Stamp, Stamp.id == StampSubmission.stamp_id)
            .join(Activity, Activity.id == Stamp.activity_id)
            .join(Passport, Passport.id == StampSubmission.passport_id)
            .join(User, User.id == Passport.user_id)
            .where(
                StampSubmission.status == SubmissionStatus.approved,
                StampSubmission.share_to_feed.is_(True),
            )
        )
        if user_id is not None:
            query = query.where(Passport.user_id == user_id)
        query = (
            query.order_by(StampSubmission.reviewed_at.desc(), StampSubmission.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list((await self.session.execute(query)).all())

    async def visible_feed_item(self, item_id: int):
        return await self.session.scalar(
            select(StampSubmission).where(
                StampSubmission.id == item_id,
                StampSubmission.status == SubmissionStatus.approved,
                StampSubmission.share_to_feed.is_(True),
            )
        )

    async def feed_engagement(self, submission_id: int, user_id: int | None = None):
        like_count = await self.session.scalar(
            select(func.count(FeedLike.id)).where(FeedLike.submission_id == submission_id)
        )
        comment_count = await self.session.scalar(
            select(func.count(FeedComment.id)).where(FeedComment.submission_id == submission_id)
        )
        liked = False
        if user_id is not None:
            liked = bool(
                await self.session.scalar(
                    select(exists().where(
                        FeedLike.submission_id == submission_id,
                        FeedLike.user_id == user_id,
                    ))
                )
            )
        return int(like_count or 0), int(comment_count or 0), liked

    async def add_like(self, submission_id: int, user_id: int):
        existing = await self.session.scalar(
            select(FeedLike).where(
                FeedLike.submission_id == submission_id, FeedLike.user_id == user_id
            )
        )
        if not existing:
            self.session.add(FeedLike(submission_id=submission_id, user_id=user_id))
            await self.session.flush()

    async def remove_like(self, submission_id: int, user_id: int):
        await self.session.execute(
            delete(FeedLike).where(
                FeedLike.submission_id == submission_id, FeedLike.user_id == user_id
            )
        )

    async def list_comments(self, submission_id: int, *, offset: int = 0, limit: int = 100):
        query = (
            select(FeedComment, User)
            .join(User, User.id == FeedComment.user_id)
            .where(FeedComment.submission_id == submission_id)
            .order_by(FeedComment.created_at.asc(), FeedComment.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return list((await self.session.execute(query)).all())

    async def add_comment(self, submission_id: int, user_id: int, content: str):
        comment = FeedComment(
            submission_id=submission_id, user_id=user_id, content=content
        )
        self.session.add(comment)
        await self.session.flush()
        await self.session.refresh(comment)
        user = await self.session.get(User, user_id)
        return comment, user

    async def update_feed_visibility(
        self,
        row: StampSubmission,
        *,
        share_to_feed: bool,
        feed_caption: str | None,
    ):
        row.share_to_feed = share_to_feed
        row.feed_caption = feed_caption if share_to_feed else None
        await self.session.flush()
        await self.session.refresh(row)
        return row

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
