from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.deps.auth import LoginUser, require_admin, require_user
from app.models import RewardClaimStatus, RewardMilestone
from app.schemas.common import Pagination
from app.schemas.me import (
    ActivityHistoryResponse,
    ActivityHistoryStatus,
    MeBadgeResponse,
    RewardClaimCreate,
    RewardClaimPatch,
    RewardClaimResponse,
    SavedActivityResponse,
)
from app.services.me import get_me_service

router = APIRouter(prefix="/api/me", tags=["My page"])
admin_router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/badges", response_model=list[MeBadgeResponse])
async def badges(
    pagination: Annotated[Pagination, Depends()],
    actor: LoginUser = Depends(require_user),
    service=Depends(get_me_service),
):
    return await service.badges(actor, offset=pagination.offset, limit=pagination.size)


@router.get("/saved-activities", response_model=list[SavedActivityResponse])
async def saved_activities(
    pagination: Annotated[Pagination, Depends()],
    events_only: bool = Query(default=False, alias="eventsOnly"),
    actor: LoginUser = Depends(require_user),
    service=Depends(get_me_service),
):
    return await service.saved_activities(
        actor, offset=pagination.offset, limit=pagination.size, events_only=events_only
    )


@router.post(
    "/saved-activities/{activity_id}",
    response_model=SavedActivityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_activity(
    activity_id: int = Path(gt=0),
    actor: LoginUser = Depends(require_user),
    service=Depends(get_me_service),
):
    return await service.save_activity(activity_id, actor)


@router.delete("/saved-activities/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_saved_activity(
    activity_id: int = Path(gt=0),
    actor: LoginUser = Depends(require_user),
    service=Depends(get_me_service),
) -> Response:
    await service.remove_saved_activity(activity_id, actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/activity-history", response_model=list[ActivityHistoryResponse])
async def activity_history(
    pagination: Annotated[Pagination, Depends()],
    q: str | None = Query(default=None, max_length=100),
    history_status: ActivityHistoryStatus | None = Query(default=None, alias="status"),
    actor: LoginUser = Depends(require_user),
    service=Depends(get_me_service),
):
    return await service.activity_history(
        actor,
        q=q,
        status=history_status.value if history_status else None,
        offset=pagination.offset,
        limit=pagination.size,
    )


@router.get("/activity-history/{history_id}", response_model=ActivityHistoryResponse)
async def activity_history_item(
    history_id: int = Path(gt=0),
    actor: LoginUser = Depends(require_user),
    service=Depends(get_me_service),
):
    return await service.activity_history_item(history_id, actor)


@router.get("/rewards", response_model=list[RewardClaimResponse])
async def rewards(
    pagination: Annotated[Pagination, Depends()],
    actor: LoginUser = Depends(require_user),
    service=Depends(get_me_service),
):
    return await service.rewards(actor, offset=pagination.offset, limit=pagination.size)


@router.post(
    "/rewards/{milestone}/claim",
    response_model=RewardClaimResponse,
    status_code=status.HTTP_201_CREATED,
)
async def claim_reward(
    body: RewardClaimCreate,
    milestone: RewardMilestone,
    actor: LoginUser = Depends(require_user),
    service=Depends(get_me_service),
):
    return await service.claim_reward(milestone, body, actor)


@admin_router.get("/reward-claims", response_model=list[RewardClaimResponse])
async def reward_claims(
    pagination: Annotated[Pagination, Depends()],
    claim_status: RewardClaimStatus | None = Query(default=None, alias="status"),
    _: LoginUser = Depends(require_admin),
    service=Depends(get_me_service),
):
    return await service.admin_reward_claims(
        claim_status, offset=pagination.offset, limit=pagination.size
    )


@admin_router.patch("/reward-claims/{claim_id}", response_model=RewardClaimResponse)
async def update_reward_claim(
    body: RewardClaimPatch,
    claim_id: int = Path(gt=0),
    _: LoginUser = Depends(require_admin),
    service=Depends(get_me_service),
):
    return await service.update_reward_claim(claim_id, body)
