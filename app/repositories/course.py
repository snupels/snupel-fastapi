from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activity, ActivityCategory, Course, CourseStamp, Stamp
from app.repositories.base import CrudRepository, dumped


class CourseRepository(CrudRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Course, self._values)

    @staticmethod
    def _values(body):
        values = dumped(body)
        for key in ("representative_image_url", "official_url"):
            if values.get(key) is not None:
                values[key] = str(values[key])
        return values

    async def create_generated_mission(self, body, stops) -> Course | None:
        activity_ids = [stop["activity_id"] for stop in stops]
        stamp_rows = (
            await self.session.execute(
                select(Stamp.activity_id, func.min(Stamp.id).label("stamp_id"))
                .where(Stamp.activity_id.in_(activity_ids))
                .group_by(Stamp.activity_id)
            )
        ).all()
        stamp_ids = dict(stamp_rows)
        if len(stamp_ids) != len(activity_ids):
            return None

        course = Course(
            category=ActivityCategory.sports if body.sport else ActivityCategory.tour,
            sport_name=body.sport,
            theme=body.theme,
            title=body.title,
            description=body.description,
            estimated_duration_minutes=sum(stop["estimated_minutes"] for stop in stops),
            is_published=False,
        )
        self.session.add(course)
        await self.session.flush()
        for position, stop in enumerate(stops, start=1):
            self.session.add(
                CourseStamp(
                    course_id=course.id,
                    stamp_id=stamp_ids[stop["activity_id"]],
                    position=position,
                )
            )
        await self.session.flush()
        await self.session.refresh(course)
        return course

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
