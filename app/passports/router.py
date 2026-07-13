from app.router import create_crud_router

from .dto import PassportCreate, PassportPatch, PassportResponse
from .service import get_passport_service

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

