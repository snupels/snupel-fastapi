from app.routes.base import create_crud_router

from app.schemas.collected_badge import (
    CollectedBadgeCreate,
    CollectedBadgePatch,
    CollectedBadgeResponse,
)
from app.services.collected_badge import get_collected_badge_service

router = create_crud_router(
    prefix="/api/collected-badges",
    tag="Collected badges",
    create_model=CollectedBadgeCreate,
    patch_model=CollectedBadgePatch,
    response_model=CollectedBadgeResponse,
    service_dependency=get_collected_badge_service,
    read_access="admin",
    detail_access="user",
)
