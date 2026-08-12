from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activity, Course, CourseStamp, Stamp
from app.repositories.base import CrudRepository, dumped


class CourseRepository(CrudRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Course, self._values)

    @staticmethod
    def _values(body):
        values = dumped(body)
        if values.get("representative_image_url") is not None:
            values["representative_image_url"] = str(values["representative_image_url"])
        return values

    async def itinerary(self, course_id: int):
        rows = await self.session.execute(
            select(
                CourseStamp.position,
                CourseStamp.stamp_id,
                Activity.id.label("activity_id"),
                Activity.category,
                Activity.place_name,
                Activity.sport_name,
                Activity.address,
                Activity.latitude,
                Activity.longitude,
                Activity.source_metadata,
            )
            .join(Stamp, Stamp.id == CourseStamp.stamp_id)
            .join(Activity, Activity.id == Stamp.activity_id)
            .where(CourseStamp.course_id == course_id)
            .order_by(CourseStamp.position, CourseStamp.id)
        )
        return rows.mappings().all()
