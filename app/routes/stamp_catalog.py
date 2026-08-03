from typing import Annotated

from fastapi import APIRouter, Depends

from app.deps.auth import optional_user
from app.schemas.common import Pagination
from app.schemas.stamp_catalog import StampCatalogResponse
from app.services.stamp_catalog import get_stamp_catalog_service

router = APIRouter(prefix="/api/stamp-catalog", tags=["Stamp catalog"])


@router.get("", response_model=list[StampCatalogResponse])
async def list_stamps(
    pagination: Annotated[Pagination, Depends()],
    _actor=Depends(optional_user),
    service=Depends(get_stamp_catalog_service),
):
    return await service.list(_actor, offset=pagination.offset, limit=pagination.size)
