from app.router import create_crud_router

from .dto import BadgeCreate, BadgePatch, BadgeResponse
from .service import get_badge_service

router = create_crud_router(
    prefix="/api/badges",
    tag="Badges",
    create_model=BadgeCreate,
    patch_model=BadgePatch,
    response_model=BadgeResponse,
    service_dependency=get_badge_service,
)

