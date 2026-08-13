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

    async def itinerary(self, item_id: int):
        course = await self.get(item_id)
        stops = []
        for row in await self.repository.itinerary(item_id):
            try:
                minutes = max(1, int((row["source_metadata"] or {}).get("duration_minutes", 60)))
            except (TypeError, ValueError):
                minutes = 60
            stops.append(
                {
                    key: row[key]
                    for key in (
                        "position",
                        "stamp_id",
                        "activity_id",
                        "category",
                        "place_name",
                        "sport_name",
                        "address",
                        "latitude",
                        "longitude",
                    )
                }
                | {"estimated_minutes": minutes}
            )
        return {
            key: getattr(course, key)
            for key in (
                "id",
                "title",
                "description",
                "category",
                "sport_name",
                "theme",
                "recommended_companion",
            )
        } | {
            "estimated_duration_minutes": course.estimated_duration_minutes
            or sum(stop["estimated_minutes"] for stop in stops),
            "stops": stops,
        }


def get_course_service(session: AsyncSession = Depends(get_session)) -> CourseService:
    return CourseService(CourseRepository(session), "Course")
