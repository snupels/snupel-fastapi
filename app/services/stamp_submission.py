from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config.database import get_session
from app.deps.auth import LoginUser
from app.exceptions import ApiError
from app.models import SubmissionStatus
from app.repositories.stamp_submission import StampSubmissionRepository
from app.services.storage import ProofStorage, get_proof_storage


class StampSubmissionService:
    def __init__(self, repository: StampSubmissionRepository, storage: ProofStorage) -> None:
        self.repository = repository
        self.storage = storage

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
        await self._target(body.passport_id, body.stamp_id, user.id)
        return self.storage.upload(body.passport_id, body.stamp_id, body.content_type)

    async def create(self, body, user: LoginUser):
        await self._target(body.passport_id, body.stamp_id, user.id)
        prefix = f"proofs/{body.passport_id}/{body.stamp_id}/"
        if not body.object_key.startswith(prefix):
            raise ApiError(400, "bad_request", "Invalid proof object key.")
        await run_in_threadpool(self.storage.validate, body.object_key)
        await self._target(body.passport_id, body.stamp_id, user.id, lock=True)
        return self._response(
            await self.repository.create(
                body.passport_id,
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
        } | {"proof_url": self.storage.proof_url(row.object_key)}

    async def list_user(
        self, user: LoginUser, *, offset: int = 0, limit: int = 20
    ):
        rows = await self.repository.list_user(user.id, offset=offset, limit=limit)
        return [self._response(row) for row in rows]

    def _profile_url(self, user) -> str | None:
        key = getattr(user, "profile_image_key", None) if user else None
        return self.storage.proof_url(key) if key else None

    def _comment_response(self, comment, user):
        return {
            "id": comment.id,
            "author_name": getattr(user, "nickname", None) or "강원 스포츠 탐험가",
            "author_profile_image_url": self._profile_url(user),
            "content": comment.content,
            "created_at": comment.created_at,
        }

    async def _feed_response(self, row, activity, author=None, viewer_id=None):
        engagement = getattr(self.repository, "feed_engagement", None)
        like_count, comment_count, liked_by_me = (
            await engagement(row.id, viewer_id) if engagement else (0, 0, False)
        )
        return {
            "id": row.id,
            "proof_url": self.storage.proof_url(row.object_key),
            "caption": row.feed_caption,
            "author_name": getattr(author, "nickname", None) or "강원 스포츠 탐험가",
            "author_profile_image_url": self._profile_url(author),
            "place_name": activity.place_name,
            "sigun": activity.sigun,
            "sport_name": activity.sport_name,
            "approved_at": row.reviewed_at,
            "like_count": like_count,
            "comment_count": comment_count,
            "liked_by_me": liked_by_me,
        }

    async def list_feed(
        self,
        *,
        user: LoginUser | None = None,
        offset: int = 0,
        limit: int = 20,
    ):
        rows = await self.repository.list_feed(
            user_id=user.id if user else None,
            offset=offset,
            limit=limit,
        )
        result = []
        for item in rows:
            row, activity, *authors = item
            result.append(
                await self._feed_response(
                    row, activity, authors[0] if authors else None, user.id if user else None
                )
            )
        return result

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
        return self._response(reviewed)


def get_stamp_submission_service(
    session: AsyncSession = Depends(get_session),
    storage: ProofStorage = Depends(get_proof_storage),
) -> StampSubmissionService:
    return StampSubmissionService(StampSubmissionRepository(session), storage)
