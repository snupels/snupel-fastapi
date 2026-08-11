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
                body.passport_id, body.stamp_id, body.object_key
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
