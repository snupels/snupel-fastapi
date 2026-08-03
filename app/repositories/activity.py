from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activity, Course, CourseStamp, Stamp
from app.models import ActivityCategory
from app.repositories.base import CrudRepository, dumped


class ActivityRepository(CrudRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Activity, self._values)

    @staticmethod
    def _values(body):
        values = dumped(body)
        for key in ("representative_image_url", "source_url"):
            if values.get(key) is not None:
                values[key] = str(values[key])
        if "metadata" in values:
            values["source_metadata"] = values.pop("metadata")
        return values

    @staticmethod
    def _available():
        cutoff = datetime.now() - timedelta(days=10)
        return and_(
            Activity.is_active.is_(True),
            or_(Activity.source.is_(None), Activity.last_synced_at >= cutoff),
            or_(Activity.ends_at.is_(None), Activity.ends_at >= datetime.now()),
        )

    async def list(self, *, offset: int = 0, limit: int = 20) -> list[Activity]:
        return list(
            await self.session.scalars(
                select(Activity)
                .where(self._available())
                .order_by(Activity.id)
                .offset(offset)
                .limit(limit)
            )
        )

    async def get(self, item_id: int):
        return await self.session.scalar(
            select(Activity).where(Activity.id == item_id, self._available())
        )

    async def explore(
        self,
        *,
        region: str | None,
        sport: str | None,
        theme: str | None,
        mission: bool | None,
        categories: tuple[str, ...] = ("sports",),
        offset: int = 0,
        limit: int = 20,
    ):
        activity_ids = (
            select(Activity.id)
            .where(Activity.category.in_(categories), self._available())
            .order_by(Activity.id)
        )
        published_course = (
            select(CourseStamp.id)
            .select_from(Stamp)
            .join(CourseStamp, CourseStamp.stamp_id == Stamp.id)
            .join(Course, Course.id == CourseStamp.course_id)
            .where(
                Stamp.activity_id == Activity.id,
                Course.is_published.is_(True),
            )
            .correlate(Activity)
        )
        if region:
            activity_ids = activity_ids.where(Activity.region == region)
        if sport:
            activity_ids = activity_ids.where(Activity.sport_name == sport)
        if theme:
            activity_ids = activity_ids.where(
                published_course.where(Course.theme == theme).exists()
            )
        if mission is True:
            activity_ids = activity_ids.where(published_course.exists())
        elif mission is False:
            activity_ids = activity_ids.where(~published_course.exists())
        activity_ids = activity_ids.offset(offset).limit(limit).subquery()
        query = (
            select(Activity, Course.theme)
            .join(activity_ids, activity_ids.c.id == Activity.id)
            .outerjoin(Stamp, Stamp.activity_id == Activity.id)
            .outerjoin(CourseStamp, CourseStamp.stamp_id == Stamp.id)
            .outerjoin(
                Course,
                and_(Course.id == CourseStamp.course_id, Course.is_published.is_(True)),
            )
            .order_by(Activity.id)
        )
        if theme:
            query = query.where(Course.theme == theme)
        return (await self.session.execute(query)).all()

    async def map_items(
        self,
        *,
        south: float,
        west: float,
        north: float,
        east: float,
        category: ActivityCategory | None,
        sport: str | None,
        mission: bool | None,
        limit: int,
    ):
        activity_ids = select(Activity.id).where(
            self._available(),
            Activity.latitude.is_not(None),
            Activity.longitude.is_not(None),
            Activity.latitude.between(south, north),
            Activity.longitude.between(west, east),
        )
        published_course = (
            select(CourseStamp.id)
            .select_from(Stamp)
            .join(CourseStamp, CourseStamp.stamp_id == Stamp.id)
            .join(Course, Course.id == CourseStamp.course_id)
            .where(Stamp.activity_id == Activity.id, Course.is_published.is_(True))
            .correlate(Activity)
        )
        if category:
            activity_ids = activity_ids.where(Activity.category == category)
        if sport:
            activity_ids = activity_ids.where(Activity.sport_name == sport)
        if mission is True:
            activity_ids = activity_ids.where(published_course.exists())
        elif mission is False:
            activity_ids = activity_ids.where(~published_course.exists())
        activity_ids = activity_ids.order_by(Activity.id).limit(limit).subquery()
        query = (
            select(Activity.id, Activity.category, Activity.place_name, Activity.sport_name,
                   Activity.latitude, Activity.longitude, published_course.exists().label("has_mission"))
            .join(activity_ids, activity_ids.c.id == Activity.id)
            .order_by(Activity.id)
        )
        return (await self.session.execute(query)).mappings().all()

    async def recommendation_candidates(
        self, region: str, sport: str | None, theme: str, limit: int = 30
    ):
        query = select(Activity).where(self._available(), Activity.region == region)
        if sport:
            query = query.where(Activity.sport_name == sport)
        theme_match = exists().where(
            Stamp.activity_id == Activity.id,
            CourseStamp.stamp_id == Stamp.id,
            Course.id == CourseStamp.course_id,
            Course.is_published.is_(True),
            Course.theme == theme,
        )
        return list(
            await self.session.scalars(
                query.order_by(theme_match.desc(), Activity.id).limit(limit)
            )
        )

    async def sync_source(self, source: str, items: list[dict], synced_at: datetime) -> int:
        existing = {
            row.external_id: row
            for row in await self.session.scalars(select(Activity).where(Activity.source == source))
        }
        seen = set()
        for values in items:
            external_id = values["external_id"]
            if not external_id:
                raise ValueError(f"{source} item is missing an external ID")
            seen.add(external_id)
            row = existing.get(external_id)
            values = values | {
                "source": source,
                "last_synced_at": synced_at,
                "is_active": True,
            }
            values["category"] = ActivityCategory(values["category"])
            if row:
                for key, value in values.items():
                    setattr(row, key, value)
            else:
                row = Activity(**values)
                self.session.add(row)
                existing[external_id] = row
        for external_id, row in existing.items():
            if external_id not in seen:
                row.is_active = False
        await self.session.flush()
        return len(items)
