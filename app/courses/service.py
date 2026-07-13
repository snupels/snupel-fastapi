from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.service import CrudService

from .repository import CourseRepository


def get_course_service(session: AsyncSession = Depends(get_session)) -> CrudService:
    return CrudService(CourseRepository(session), "Course")
