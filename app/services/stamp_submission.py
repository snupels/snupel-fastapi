from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config.database import get_session
from app.config import admins
from app.deps.auth import LoginUser
from app.exceptions import ApiError
from app.models import SubmissionStatus
from app.repositories.stamp_submission import StampSubmissionRepository
from app.services.storage import ProofStorage, get_proof_storage


class StampSubmissionService:
    def __init__(self, repository: StampSubmissionRepository, storage: ProofStorage) -> None:
        self.repository = repository
        self.storage = storage

    async def _passport_id(self, requested_id: int | None, user_id: int) -> int:
        passport_id = requested_id or await self.repository.passport_id(user_id)
        if passport_id is None:
            raise ApiError(404, "not_found", "Passport not found.")
        return passport_id

    async def _target(
        self, passport_id: int, stamp_id: int, user_id: int, *, lock: bool = False
    ) -> None:
        if not await self.repository.valid_target(
            passport_id, stamp_id, user_id, lock=lock
        ):
            raise ApiError(404, "not_found", "Published passport mission stamp not found.")
        if await self.repository.collected(passport_id, stamp_id):
            raise ApiError(409, "conflict", "Stamp is already collected.")
        if await self.repository.pending(passport_id, stamp_id):
            raise ApiError(409, "conflict", "A proof is already pending.")

    async def upload_url(self, body, user: LoginUser):
        passport_id = await self._passport_id(body.passport_id, user.id)
        await self._target(passport_id, body.stamp_id, user.id)
        return self.storage.upload(passport_id, body.stamp_id, body.content_type)

    async def create(self, body, user: LoginUser):
        passport_id = await self._passport_id(body.passport_id, user.id)
        await self._target(passport_id, body.stamp_id, user.id)
        prefix = f"proofs/{passport_id}/{body.stamp_id}/"
        if not body.object_key.startswith(prefix):
            raise ApiError(400, "bad_request", "Invalid proof object key.")
        await run_in_threadpool(self.storage.validate, body.object_key)
        await self._target(passport_id, body.stamp_id, user.id, lock=True)
        return self._response(
            await self.repository.create(
                passport_id,
                body.stamp_id,
                body.object_key,
                share_to_feed=body.share_to_feed,
                feed_caption=body.feed_caption if body.share_to_feed else None,
            )
        )

    def _response(self, row):
        return {
            key: getattr(row, key)
            for key in (
                "id",
                "passport_id",
                "stamp_id",
                "object_key",
                "share_to_feed",
                "feed_caption",
                "status",
                "reviewer_id",
                "reviewed_at",
                "rejection_reason",
                "created_at",
                "updated_at",
            )
        } | {
            "proof_url": self.storage.proof_url(row.object_key),
            "submitted_at": row.created_at,
        }

    def _user_response(self, row, activity, course_title, catalog):
        stamp_name = (
            f"{catalog.region_ko} {catalog.sport_ko}" if catalog else None
        )
        return self._response(row) | {
            "activity": activity,
            "course_title": course_title,
            "stamp_name": stamp_name,
        }

    async def list_user(
        self, user: LoginUser, *, offset: int = 0, limit: int = 20
    ):
        rows = await self.repository.list_user(user.id, offset=offset, limit=limit)
        return [self._user_response(*item) for item in rows]

    def _profile_url(self, user) -> str | None:
        key = getattr(user, "profile_image_key", None) if user else None
        return self.storage.proof_url(key) if key else None

    def _comment_response(self, comment, user):
        return {
            "id": comment.id,
            "author_id": user.id,
            "author_name": getattr(user, "nickname", None) or "강원 스포츠 탐험가",
            "author_profile_image_url": self._profile_url(user),
            "content": comment.content,
            "created_at": comment.created_at,
        }

    async def _feed_response(
        self,
        row,
        activity,
        author=None,
        viewer_id=None,
        engagement_values=None,
    ):
        if engagement_values is None:
            engagement = getattr(self.repository, "feed_engagement", None)
            engagement_values = (
                await engagement(row.id, viewer_id) if engagement else (0, 0, False)
            )
        like_count, comment_count, liked_by_me = engagement_values
        return {
            "id": row.id,
            "is_demo": bool(getattr(row, "is_demo", False)),
            "proof_url": "https://sportspassport.kr/community-demo.svg" if getattr(row, "is_demo", False) else self.storage.proof_url(row.object_key),
            "caption": row.feed_caption,
            "author_id": getattr(author, "id", 0),
            "author_name": getattr(author, "nickname", None) or "강원 스포츠 탐험가",
            "author_profile_image_url": self._profile_url(author),
            "place_name": getattr(activity, "place_name", None),
            "sigun": getattr(activity, "sigun", None),
            "sport_name": getattr(activity, "sport_name", None),
            "approved_at": row.reviewed_at,
            "like_count": like_count,
            "comment_count": comment_count,
            "liked_by_me": liked_by_me,
        }

    async def list_feed(
        self,
        *,
        user: LoginUser | None = None,
        owner_user_id: int | None = None,
        following_only: bool = False,
        liked_only: bool = False,
        item_id: int | None = None,
        offset: int = 0,
        limit: int = 20,
    ):
        extra_filters = {"following_only": True} if following_only else {}
        if liked_only:
            if not user:
                raise ApiError(401, "unauthorized", "Login required for liked feed.")
            extra_filters["liked_only"] = True
        if item_id is not None:
            extra_filters["item_id"] = item_id
        if following_only and not user:
            raise ApiError(401, "unauthorized", "Login required for following feed.")
        rows = await self.repository.list_feed(
            owner_user_id=owner_user_id,
            viewer_user_id=user.id if user else None,
            offset=offset,
            limit=limit,
            **extra_filters,
        )
        result = []
        for item in rows:
            row, activity, *extra = item
            author = extra[0] if extra else None
            engagement_values = tuple(extra[1:4]) if len(extra) >= 4 else None
            result.append(
                await self._feed_response(
                    row,
                    activity,
                    author,
                    user.id if user else None,
                    engagement_values,
                )
            )
        return result

    async def feed_detail(self, item_id: int, viewer: LoginUser | None = None):
        rows = await self.list_feed(user=viewer, item_id=item_id, limit=1)
        if not rows:
            raise ApiError(404, "not_found", "Community feed post not found.")
        return rows[0]

    async def community_profile(self, user_id: int, viewer: LoginUser | None = None):
        result = await self.repository.public_profile(user_id, viewer.id if viewer else None)
        if result is None:
            raise ApiError(404, "not_found", "User not found.")
        author, followers, following, followed = result
        return {"id": author.id, "name": author.nickname or "강원 스포츠 탐험가",
                "profile_image_url": self._profile_url(author),
                "follower_count": followers, "following_count": following,
                "followed_by_me": followed, "is_operator": author.email.lower() in admins()}

    async def follow_user(self, user_id: int, actor: LoginUser, *, following: bool):
        if user_id == actor.id:
            raise ApiError(400, "bad_request", "Cannot follow yourself.")
        await self.community_profile(user_id, actor)
        await self.repository.set_follow(actor.id, user_id, following)
        return await self.community_profile(user_id, actor)

    async def update_like(self, item_id: int, user: LoginUser, *, liked: bool):
        if not await self.repository.visible_feed_item(item_id):
            raise ApiError(404, "not_found", "Community feed post not found.")
        if liked:
            await self.repository.add_like(item_id, user.id)
        else:
            await self.repository.remove_like(item_id, user.id)
        like_count, _, liked_by_me = await self.repository.feed_engagement(item_id, user.id)
        return {"like_count": like_count, "liked_by_me": liked_by_me}

    async def list_comments(self, item_id: int, *, offset: int = 0, limit: int = 100):
        if not await self.repository.visible_feed_item(item_id):
            raise ApiError(404, "not_found", "Community feed post not found.")
        rows = await self.repository.list_comments(item_id, offset=offset, limit=limit)
        return [self._comment_response(comment, author) for comment, author in rows]

    async def add_comment(self, item_id: int, content: str, user: LoginUser):
        if not await self.repository.visible_feed_item(item_id):
            raise ApiError(404, "not_found", "Community feed post not found.")
        comment, author = await self.repository.add_comment(item_id, user.id, content)
        return self._comment_response(comment, author)

    async def update_feed_visibility(self, item_id: int, body, user: LoginUser):
        row = await self.repository.get_owned(item_id, user.id)
        if not row:
            raise ApiError(404, "not_found", "Stamp submission not found.")
        updated = await self.repository.update_feed_visibility(
            row,
            share_to_feed=body.share_to_feed,
            feed_caption=body.feed_caption,
        )
        return self._response(updated)

    async def list_admin(
        self, status: SubmissionStatus, *, offset: int = 0, limit: int = 20
    ):
        rows = await self.repository.list_status(status, offset=offset, limit=limit)
        return [self._response(row) | {"activity": activity} for row, activity in rows]

    async def review(self, item_id: int, reviewer: LoginUser, reason: str | None = None):
        row = await self.repository.get(item_id)
        if not row:
            raise ApiError(404, "not_found", "Stamp submission not found.")
        if row.status != SubmissionStatus.pending:
            raise ApiError(409, "conflict", "Stamp submission is already reviewed.")
        reviewed = (
            await self.repository.reject(row, reviewer.id, reason)
            if reason is not None
            else await self.repository.approve(row, reviewer.id)
        )
        if reason is None:
            progress = await self.repository.badge_progress(reviewed.passport_id)
            rules = set()
            if progress["missions"] >= 1:
                rules.add("first_mission")
            if progress["mountains"] >= 1:
                rules.add("first_mountain")
            if progress["regions"] >= 3:
                rules.add("three_regions")
            if progress["sports"] >= 3:
                rules.add("three_sports")
            await self.repository.award_badges(reviewed.passport_id, rules)
        return self._response(reviewed)


def get_stamp_submission_service(
    session: AsyncSession = Depends(get_session),
    storage: ProofStorage = Depends(get_proof_storage),
) -> StampSubmissionService:
    return StampSubmissionService(StampSubmissionRepository(session), storage)
