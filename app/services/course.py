from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.exceptions import ApiError
from app.models import ActivityCategory
from app.repositories.course import CourseRepository
from app.services.base import CrudService


class CourseService(CrudService):
    async def update(self, item_id: int, body, user=None):
        row = await self.get(item_id, user)
        category = body.category if "category" in body.model_fields_set else row.category
        sport_name = body.sport_name if "sport_name" in body.model_fields_set else row.sport_name
        if category == ActivityCategory.sports and not sport_name:
            raise ApiError(400, "bad_request", "sport_name is required for sports courses")
        if category != ActivityCategory.sports and sport_name is not None:
            raise ApiError(400, "bad_request", "sport_name is only allowed for sports courses")
        return await self.repository.update(row, body)


def get_course_service(session: AsyncSession = Depends(get_session)) -> CourseService:
    return CourseService(CourseRepository(session), "Course")
