from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.deps.auth import LoginUser, require_admin, require_user
from app.schemas.common import Pagination
from app.schemas.passport_reward import (
    TeeClaimCreate,
    TeeClaimPatch,
    TeeClaimResponse,
    TeeRewardResponse,
)
from app.services.passport_reward import get_passport_reward_service

router = APIRouter(prefix="/api", tags=["Passport tee rewards"])


@router.get("/me/passport-rewards/tee", response_model=TeeRewardResponse)
async def reward_status(
    actor: LoginUser = Depends(require_user), service=Depends(get_passport_reward_service)
):
    return await service.status(actor)


@router.post("/me/passport-rewards/tee/claim", response_model=TeeClaimResponse, status_code=201)
async def claim(
    body: TeeClaimCreate,
    actor: LoginUser = Depends(require_user),
    service=Depends(get_passport_reward_service),
):
    return await service.claim(body, actor)


@router.get("/admin/passport-tee-claims", response_model=list[TeeClaimResponse])
async def admin_claims(
    pagination: Annotated[Pagination, Depends()],
    _: LoginUser = Depends(require_admin),
    service=Depends(get_passport_reward_service),
):
    return await service.admin_claims(offset=pagination.offset, limit=pagination.size)


@router.patch("/admin/passport-tee-claims/{claim_id}", response_model=TeeClaimResponse)
async def update_claim(
    body: TeeClaimPatch,
    claim_id: int = Path(gt=0),
    _: LoginUser = Depends(require_admin),
    service=Depends(get_passport_reward_service),
):
    return await service.update(claim_id, body)
