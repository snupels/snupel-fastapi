from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.repositories.course import CourseRepository
from app.services.base import CrudService


def get_course_service(session: AsyncSession = Depends(get_session)) -> CrudService:
    return CrudService(CourseRepository(session), "Course")
