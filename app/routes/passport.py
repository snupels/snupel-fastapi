from typing import Annotated

from fastapi import Depends, Path

from app.deps.auth import optional_user
from app.routes.base import create_crud_router

from app.schemas.passport import MissionProgress, PassportCreate, PassportPatch, PassportResponse
from app.schemas.common import Pagination
from app.services.passport import get_passport_service

router = create_crud_router(
    prefix="/api/passports",
    tag="Passports",
    create_model=PassportCreate,
    patch_model=PassportPatch,
    response_model=PassportResponse,
    service_dependency=get_passport_service,
)


@router.get("/{item_id}/missions", response_model=list[MissionProgress])
async def passport_missions(
    pagination: Annotated[Pagination, Depends()],
    item_id: int = Path(gt=0),
    actor=Depends(optional_user),
    service=Depends(get_passport_service),
):
    return await service.missions(
        item_id, actor, offset=pagination.offset, limit=pagination.size
    )
