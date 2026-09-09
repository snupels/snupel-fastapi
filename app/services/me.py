from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.deps.auth import LoginUser
from app.exceptions import ApiError
from app.models import RewardClaimStatus, RewardMilestone
from app.repositories.me import MeRepository
from app.services.storage import ProofStorage, get_proof_storage

REWARD_BADGES = {RewardMilestone.badge_6: 6, RewardMilestone.badge_12: 12}
HISTORY_CODES = {"submission": 1, "stamp": 2, "saved": 3}
HISTORY_FEED_TYPES = ("submission", "stamp")


class MeService:
    def __init__(self, repository: MeRepository, storage: ProofStorage) -> None:
        self.repository = repository
        self.storage = storage

    async def badges(self, user: LoginUser, *, offset: int, limit: int):
        return await self.repository.badges(user.id, offset=offset, limit=limit)

    @staticmethod
    def _saved_response(row, activity):
        return {
            "id": row.id,
            "activity_id": row.activity_id,
            "created_at": row.created_at,
            "activity": activity,
        }

    async def saved_activities(self, user: LoginUser, *, offset: int, limit: int, events_only: bool = False):
        rows = await self.repository.saved_activities(user.id, offset=offset, limit=limit, events_only=events_only)
        return [self._saved_response(row, activity) for row, activity in rows]

    async def save_activity(self, activity_id: int, user: LoginUser):
        if not await self.repository.activity_exists(activity_id):
            raise ApiError(404, "not_found", "Activity not found.")
        if await self.repository.saved_activity(user.id, activity_id):
            raise ApiError(409, "conflict", "Activity is already saved.")
        try:
            return self._saved_response(
                *(await self.repository.save_activity(user.id, activity_id))
            )
        except IntegrityError as error:
            raise ApiError(409, "conflict", "Activity is already saved.") from error

    async def remove_saved_activity(self, activity_id: int, user: LoginUser) -> None:
        row = await self.repository.saved_activity(user.id, activity_id)
        if not row:
            raise ApiError(404, "not_found", "Saved activity not found.")
        await self.repository.remove_saved_activity(row)

    def _history_response(self, kind: str, row):
        code = HISTORY_CODES[kind]
        data = dict(row)
        data.update(
            id=data.pop("source_id") * 10 + code,
            type=kind,
            status=data.get("status", "collected"),
            submission_id=data.get("submission_id"),
            rejection_reason=data.get("rejection_reason"),
        )
        if kind == "submission":
            data["image_url"] = self.storage.proof_url(data.pop("object_key"))
        return data

    async def activity_history(
        self,
        user: LoginUser,
        *,
        q: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ):
        q = q.strip() if q else None
        groups = await self.repository.activity_history(
            user.id, q=q, status=status, limit=offset + limit
        )
        rows = [
            self._history_response(kind, row)
            for kind, group in zip(HISTORY_FEED_TYPES, groups, strict=True)
            for row in group
        ]
        rows.sort(key=lambda row: (row["occurred_at"], row["id"]), reverse=True)
        return rows[offset : offset + limit]

    async def activity_history_item(self, history_id: int, user: LoginUser):
        codes = {value: key for key, value in HISTORY_CODES.items()}
        kind = codes.get(history_id % 10)
        source_id = history_id // 10
        if not kind or source_id < 1:
            raise ApiError(404, "not_found", "Activity history not found.")
        row = await self.repository.activity_history_item(user.id, kind, source_id)
        if not row:
            raise ApiError(404, "not_found", "Activity history not found.")
        return self._history_response(kind, row)

    async def rewards(self, user: LoginUser, *, offset: int, limit: int):
        count = await self.repository.badge_count(user.id)
        claims = {claim.milestone: claim for claim in await self.repository.reward_claims(user.id)}
        rewards = [
            claims.get(milestone)
            or {
                "user_id": user.id,
                "milestone": milestone,
                "status": RewardClaimStatus.eligible,
            }
            for milestone, required in REWARD_BADGES.items()
            if count >= required or milestone in claims
        ]
        return rewards[offset : offset + limit]

    async def claim_reward(self, milestone: RewardMilestone, body, user: LoginUser):
        if await self.repository.badge_count(user.id) < REWARD_BADGES[milestone]:
            raise ApiError(409, "not_eligible", "Reward milestone is not yet eligible.")
        if await self.repository.reward_claim(user.id, milestone):
            raise ApiError(409, "conflict", "Reward is already claimed.")
        try:
            return await self.repository.create_reward_claim(user.id, milestone, body)
        except IntegrityError as error:
            raise ApiError(409, "conflict", "Reward is already claimed.") from error

    async def admin_reward_claims(
        self, status: RewardClaimStatus | None, *, offset: int, limit: int
    ):
        return await self.repository.admin_reward_claims(status, offset=offset, limit=limit)

    async def update_reward_claim(self, claim_id: int, body):
        row = await self.repository.get_reward_claim(claim_id)
        if not row:
            raise ApiError(404, "not_found", "Reward claim not found.")
        return await self.repository.update_reward_claim(row, body.status)


def get_me_service(
    session: AsyncSession = Depends(get_session),
    storage: ProofStorage = Depends(get_proof_storage),
) -> MeService:
    return MeService(MeRepository(session), storage)
