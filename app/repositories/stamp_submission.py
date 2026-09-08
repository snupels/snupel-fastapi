from datetime import datetime

from sqlalchemy import case, delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Activity,
    Badge,
    CollectedBadge,
    CollectedStamp,
    Course,
    CourseStamp,
    FeedComment,
    FeedLike,
    Passport,
    Stamp,
    StampCatalog,
    StampSubmission,
    SubmissionStatus,
    User,
    UserFollow,
)


class StampSubmissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def passport_id(self, user_id: int) -> int | None:
        return await self.session.scalar(
            select(Passport.id).where(Passport.user_id == user_id)
        )

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
        course_title = (
            select(Course.title)
            .join(CourseStamp, CourseStamp.course_id == Course.id)
            .where(CourseStamp.stamp_id == Stamp.id, Course.is_published.is_(True))
            .order_by(Course.id)
            .limit(1)
            .scalar_subquery()
        )
        return list(
            (
                await self.session.execute(
                    select(StampSubmission, Activity, course_title, StampCatalog)
                .join(Passport, Passport.id == StampSubmission.passport_id)
                .join(Stamp, Stamp.id == StampSubmission.stamp_id)
                .join(Activity, Activity.id == Stamp.activity_id)
                .outerjoin(StampCatalog, StampCatalog.id == Stamp.stamp_catalog_id)
                .where(Passport.user_id == user_id)
                .order_by(StampSubmission.id.desc())
                .offset(offset)
                .limit(limit)
                )
            )
            .all()
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
        owner_user_id: int | None = None,
        viewer_user_id: int | None = None,
        following_only: bool = False,
        liked_only: bool = False,
        item_id: int | None = None,
        offset: int = 0,
        limit: int = 20,
    ):
        like_count = (
            select(func.count(FeedLike.id))
            .where(FeedLike.submission_id == StampSubmission.id)
            .correlate(StampSubmission)
            .scalar_subquery()
        )
        comment_count = (
            select(func.count(FeedComment.id))
            .where(FeedComment.submission_id == StampSubmission.id)
            .correlate(StampSubmission)
            .scalar_subquery()
        )
        liked_by_me = (
            select(exists().where(
                FeedLike.submission_id == StampSubmission.id,
                FeedLike.user_id == viewer_user_id,
            )).scalar_subquery()
            if viewer_user_id is not None
            else False
        )
        query = (
            select(
                StampSubmission,
                Activity,
                User,
                like_count.label("like_count"),
                comment_count.label("comment_count"),
                liked_by_me.label("liked_by_me") if viewer_user_id is not None else liked_by_me,
            )
            .outerjoin(Stamp, Stamp.id == StampSubmission.stamp_id)
            .outerjoin(Activity, Activity.id == Stamp.activity_id)
            .outerjoin(Passport, Passport.id == StampSubmission.passport_id)
            .join(User, User.id == func.coalesce(Passport.user_id, StampSubmission.author_id))
            .where(
                StampSubmission.status == SubmissionStatus.approved,
                StampSubmission.share_to_feed.is_(True),
            )
        )
        if owner_user_id is not None:
            query = query.where(User.id == owner_user_id)
        if item_id is not None:
            query = query.where(StampSubmission.id == item_id)
        if liked_only:
            query = query.where(exists().where(
                FeedLike.submission_id == StampSubmission.id,
                FeedLike.user_id == viewer_user_id,
            ))
        if following_only:
            query = query.where(exists().where(
                UserFollow.follower_id == viewer_user_id, UserFollow.followed_id == User.id
            ))
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

    async def public_profile(self, user_id: int, viewer_id: int | None):
        user = await self.session.get(User, user_id)
        if user is None:
            return None
        followers = await self.session.scalar(select(func.count()).select_from(UserFollow).where(UserFollow.followed_id == user_id))
        following = await self.session.scalar(select(func.count()).select_from(UserFollow).where(UserFollow.follower_id == user_id))
        followed = bool(await self.session.scalar(select(exists().where(
            UserFollow.follower_id == viewer_id, UserFollow.followed_id == user_id
        )))) if viewer_id else False
        return user, followers, following, followed

    async def set_follow(self, follower_id: int, followed_id: int, following: bool):
        # Serialize actions by actor so repeated/concurrent requests remain idempotent.
        await self.session.scalar(select(User.id).where(User.id == follower_id).with_for_update())
        row = await self.session.get(UserFollow, (follower_id, followed_id))
        if following and row is None:
            self.session.add(UserFollow(follower_id=follower_id, followed_id=followed_id))
        elif not following and row is not None:
            await self.session.delete(row)
        await self.session.flush()

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
        await self.session.scalar(select(User.id).where(User.id == user_id).with_for_update())
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
        await self.session.scalar(
            select(Passport.id).where(Passport.id == row.passport_id).with_for_update()
        )
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

    async def badge_progress(self, passport_id: int):
        row = (
            await self.session.execute(
                select(
                    func.count(CollectedStamp.id).label("missions"),
                    func.count(func.distinct(Activity.sigun)).label("regions"),
                    func.count(func.distinct(Activity.sport_name)).label("sports"),
                    func.count(
                        func.distinct(
                            case(
                                (
                                    func.lower(Activity.sport_name).in_(
                                        ("hiking", "mountain", "등산")
                                    ),
                                    Activity.id,
                                )
                            )
                        )
                    ).label("mountains"),
                )
                .select_from(CollectedStamp)
                .join(Stamp, Stamp.id == CollectedStamp.stamp_id)
                .join(Activity, Activity.id == Stamp.activity_id)
                .where(CollectedStamp.passport_id == passport_id)
            )
        ).mappings().one()
        return {key: int(row[key] or 0) for key in ("missions", "regions", "sports", "mountains")}

    async def award_badges(self, passport_id: int, rule_keys: set[str]) -> None:
        if not rule_keys:
            return
        badge_ids = select(Badge.id).where(Badge.rule_key.in_(rule_keys))
        existing = select(CollectedBadge.badge_id).where(
            CollectedBadge.passport_id == passport_id
        )
        for badge_id in await self.session.scalars(badge_ids.where(Badge.id.not_in(existing))):
            self.session.add(CollectedBadge(passport_id=passport_id, badge_id=badge_id))
        await self.session.flush()

    async def reject(self, row: StampSubmission, reviewer_id: int, reason: str):
        row.status = SubmissionStatus.rejected
        row.reviewer_id = reviewer_id
        row.reviewed_at = datetime.now()
        row.rejection_reason = reason
        await self.session.flush()
        await self.session.refresh(row)
        return row
