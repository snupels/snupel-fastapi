from app.router import create_crud_router

from .dto import CollectedBadgeCreate, CollectedBadgePatch, CollectedBadgeResponse
from .service import get_collected_badge_service

router = create_crud_router(
    prefix="/api/collected-badges",
    tag="Collected badges",
    create_model=CollectedBadgeCreate,
    patch_model=CollectedBadgePatch,
    response_model=CollectedBadgeResponse,
    service_dependency=get_collected_badge_service,
    read_access="user",
    write_access="user",
)

