from app.routes.base import create_crud_router

from app.schemas.collected_stamp import (
    CollectedStampCreate,
    CollectedStampPatch,
    CollectedStampResponse,
)
from app.services.collected_stamp import get_collected_stamp_service

router = create_crud_router(
    prefix="/api/collected-stamps",
    tag="Collected stamps",
    create_model=CollectedStampCreate,
    patch_model=CollectedStampPatch,
    response_model=CollectedStampResponse,
    service_dependency=get_collected_stamp_service,
    read_access="admin",
    detail_access="user",
)
