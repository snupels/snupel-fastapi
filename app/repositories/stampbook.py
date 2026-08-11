from sqlalchemy import and_, case, exists, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CollectedStamp, Course, CourseStamp, Passport, Stamp, StampCatalog
from app.schemas.stampbook import StampbookFilter, StampbookStatus


class StampbookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def passport_id(self, user_id: int) -> int | None:
        return await self.session.scalar(select(Passport.id).where(Passport.user_id == user_id))

    @staticmethod
    def _catalog_status(passport_id: int):
        published_course = exists().where(
            CourseStamp.stamp_id == Stamp.id,
            Course.id == CourseStamp.course_id,
            Course.is_published.is_(True),
        )
        status = case(
            (
                CollectedStamp.id.is_not(None),
                literal(StampbookStatus.collected.value),
            ),
            (published_course, literal(StampbookStatus.available.value)),
            else_=literal(StampbookStatus.locked.value),
        ).label("status")
        return (
            select(
                StampCatalog.id.label("catalog_id"),
                Stamp.id.label("stamp_id"),
                StampCatalog.region_ko,
                StampCatalog.region_en,
                StampCatalog.sport_ko,
                StampCatalog.sport_en,
                StampCatalog.color,
                StampCatalog.image_key,
                CollectedStamp.collected_at,
                status,
            )
            .outerjoin(Stamp, Stamp.stamp_catalog_id == StampCatalog.id)
            .outerjoin(
                CollectedStamp,
                and_(
                    CollectedStamp.stamp_id == Stamp.id,
                    CollectedStamp.passport_id == passport_id,
                ),
            )
            .subquery()
        )

    async def stampbook(
        self,
        passport_id: int,
        status: StampbookFilter,
        *,
        offset: int,
        limit: int,
    ):
        catalog = self._catalog_status(passport_id)
        summary_row = (
            await self.session.execute(
                select(
                    func.count().label("total"),
                    func.coalesce(
                        func.sum(
                            case(
                                (catalog.c.status == StampbookStatus.collected.value, 1),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("collected"),
                    func.coalesce(
                        func.sum(
                            case(
                                (catalog.c.status == StampbookStatus.available.value, 1),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("available"),
                    func.coalesce(
                        func.sum(
                            case(
                                (catalog.c.status == StampbookStatus.locked.value, 1),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("locked"),
                )
            )
        ).mappings().one()
        summary = {key: int(summary_row[key]) for key in ("total", "collected", "available", "locked")}

        page_query = select(catalog)
        if status != StampbookFilter.all:
            page_query = page_query.where(catalog.c.status == status.value)
        page = page_query.order_by(catalog.c.catalog_id).offset(offset).limit(limit).subquery()
        published_courses = (
            select(
                CourseStamp.stamp_id,
                Course.id.label("course_id"),
                Course.title.label("course_title"),
            )
            .join(Course, Course.id == CourseStamp.course_id)
            .where(Course.is_published.is_(True))
            .subquery()
        )
        rows = (
            await self.session.execute(
                select(page, published_courses.c.course_id, published_courses.c.course_title)
                .outerjoin(published_courses, published_courses.c.stamp_id == page.c.stamp_id)
                .order_by(page.c.catalog_id, published_courses.c.course_id)
            )
        ).mappings().all()
        return summary, rows
