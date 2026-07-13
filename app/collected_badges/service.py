from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.collected import CollectedService
from app.database import get_session

from .repository import CollectedBadgeRepository


def get_collected_badge_service(session: AsyncSession = Depends(get_session)) -> CollectedService:
    return CollectedService(CollectedBadgeRepository(session), "Badge")
