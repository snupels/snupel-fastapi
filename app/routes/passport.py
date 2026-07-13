from app.routes.base import create_crud_router

from app.schemas.passport import PassportCreate, PassportPatch, PassportResponse
from app.services.passport import get_passport_service

router = create_crud_router(
    prefix="/api/passports",
    tag="Passports",
    create_model=PassportCreate,
    patch_model=PassportPatch,
    response_model=PassportResponse,
    service_dependency=get_passport_service,
    read_access="user",
    write_access="user",
)
