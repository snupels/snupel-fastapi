from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.service import CrudService

from .repository import ActivityRepository


def get_activity_service(session: AsyncSession = Depends(get_session)) -> CrudService:
    return CrudService(ActivityRepository(session), "Activity")
