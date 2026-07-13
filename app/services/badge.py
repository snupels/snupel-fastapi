from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.repositories.badge import BadgeRepository
from app.services.base import CrudService


def get_badge_service(session: AsyncSession = Depends(get_session)) -> CrudService:
    return CrudService(BadgeRepository(session), "Badge")
