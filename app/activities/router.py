from app.router import create_crud_router

from .dto import ActivityCreate, ActivityPatch, ActivityResponse
from .service import get_activity_service

router = create_crud_router(
    prefix="/api/activities",
    tag="Activities",
    create_model=ActivityCreate,
    patch_model=ActivityPatch,
    response_model=ActivityResponse,
    service_dependency=get_activity_service,
)

