from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, exists, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activity, CollectedStamp, Course, CourseStamp, Passport, Stamp
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
        sigun: str | None,
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
        if sigun:
            activity_ids = activity_ids.where(Activity.sigun == sigun)
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
        if categories == ("sports",):
            activity_ids = activity_ids.order_by(
                published_course.exists().desc(),
                func.coalesce(Activity.last_synced_at, Activity.created_at).desc(),
                Activity.id,
            )
        else:
            activity_ids = activity_ids.order_by(Activity.id)
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
        self,
        region: str,
        sigun: str | None,
        sport: str | None,
        theme: str,
        limit: int = 60,
        *,
        require_stamp: bool = False,
        user_id: int | None = None,
    ):
        theme_match = exists().where(
            Stamp.activity_id == Activity.id,
            CourseStamp.stamp_id == Stamp.id,
            Course.id == CourseStamp.course_id,
            Course.is_published.is_(True),
            Course.theme == theme,
        )
        sport_match = Activity.sport_name == sport if sport else True
        query = select(
            Activity,
            theme_match.label("theme_match"),
            sport_match.label("sport_match") if sport else literal(True),
        ).where(self._available(), Activity.region == region)
        if sigun:
            query = query.where(Activity.sigun == sigun)
        if require_stamp:
            query = query.where(exists().where(Stamp.activity_id == Activity.id))
        if user_id is not None:
            visited = (
                exists()
                .where(
                    Passport.user_id == user_id,
                    CollectedStamp.passport_id == Passport.id,
                    CollectedStamp.stamp_id == Stamp.id,
                    Stamp.activity_id == Activity.id,
                )
                .correlate(Activity)
            )
            query = query.where(~visited)
        ordering = [theme_match.desc(), Activity.id]
        if sport:
            ordering.insert(0, sport_match.desc())
        rows = (await self.session.execute(query.order_by(*ordering).limit(limit))).all()
        for activity, matches_theme, matches_sport in rows:
            activity.recommendation_theme_match = matches_theme
            activity.recommendation_sport_match = matches_sport
        return [activity for activity, _, _ in rows]

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
            metadata = values.get("source_metadata") or {}
            previous_metadata = row.source_metadata or {} if row else {}
            if (source == "tourapi" and metadata.get("hiking_lookup_failed")
                    and previous_metadata.get("hiking_routes")):
                # A transient detail lookup failure must not erase verified API routes.
                values = values | {
                    "sport_name": row.sport_name, "category": row.category,
                    "summary": row.summary,
                    "source_metadata": previous_metadata | metadata,
                }
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

    async def sports_dedup_candidates(self) -> tuple[list[Activity], set[int]]:
        rows = list(
            await self.session.scalars(
                select(Activity).where(
                    Activity.category == ActivityCategory.sports,
                    Activity.is_active.is_(True),
                    Activity.source.is_not(None),
                )
            )
        )
        protected_ids = set(
            await self.session.scalars(select(Stamp.activity_id).distinct())
        )
        return rows, protected_ids

    async def deactivate_activity_ids(self, activity_ids: set[int]) -> int:
        if not activity_ids:
            return 0
        await self.session.execute(
            update(Activity)
            .where(Activity.id.in_(activity_ids))
            .values(is_active=False)
        )
        await self.session.flush()
        return len(activity_ids)
