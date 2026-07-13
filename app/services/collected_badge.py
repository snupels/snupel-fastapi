from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.repositories.collected_badge import CollectedBadgeRepository
from app.services.collected import CollectedService


def get_collected_badge_service(session: AsyncSession = Depends(get_session)) -> CollectedService:
    return CollectedService(CollectedBadgeRepository(session), "Badge")
