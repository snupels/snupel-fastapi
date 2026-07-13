from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.service import CrudService

from .repository import BadgeRepository


def get_badge_service(session: AsyncSession = Depends(get_session)) -> CrudService:
    return CrudService(BadgeRepository(session), "Badge")
