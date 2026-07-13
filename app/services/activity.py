from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.repositories.activity import ActivityRepository
from app.services.base import CrudService


def get_activity_service(session: AsyncSession = Depends(get_session)) -> CrudService:
    return CrudService(ActivityRepository(session), "Activity")
