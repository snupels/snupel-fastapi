from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.repositories.stamp_catalog import StampCatalogRepository
from app.services.base import CrudService


def get_stamp_catalog_service(session: AsyncSession = Depends(get_session)) -> CrudService:
    return CrudService(StampCatalogRepository(session), "Stamp catalog")
