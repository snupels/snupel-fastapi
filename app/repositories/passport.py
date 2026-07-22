from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CollectedStamp, Course, CourseStamp, Passport


class PassportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self, user_id: int, *, offset: int = 0, limit: int = 20
    ) -> list[Passport]:
        query = (
            select(Passport)
            .where(Passport.user_id == user_id)
            .order_by(Passport.id)
            .offset(offset)
            .limit(limit)
        )
        return list(await self.session.scalars(query))

    async def get(self, item_id: int, user_id: int) -> Passport | None:
        return await self.session.scalar(
            select(Passport).where(Passport.id == item_id, Passport.user_id == user_id)
        )

    async def get_by_user(self, user_id: int) -> Passport | None:
        return await self.session.scalar(select(Passport).where(Passport.user_id == user_id))

    async def create(self, user_id: int) -> Passport:
        row = Passport(user_id=user_id)
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def remove(self, row: Passport) -> None:
        await self.session.delete(row)
        await self.session.flush()

    async def mission_progress(
        self, passport_id: int, *, offset: int = 0, limit: int = 20
    ) -> list[dict]:
        total = (
            select(func.count(CourseStamp.id))
            .where(CourseStamp.course_id == Course.id)
            .correlate(Course)
            .scalar_subquery()
        )
        collected = (
            select(func.count(CollectedStamp.id))
            .join(CourseStamp, CourseStamp.stamp_id == CollectedStamp.stamp_id)
            .where(
                CourseStamp.course_id == Course.id,
                CollectedStamp.passport_id == passport_id,
            )
            .correlate(Course)
            .scalar_subquery()
        )
        rows = (
            await self.session.execute(
                select(
                    Course.id.label("course_id"),
                    Course.title,
                    Course.theme,
                    total.label("total_stamps"),
                    collected.label("collected_stamps"),
                )
                .where(Course.is_published.is_(True))
                .order_by(Course.id)
                .offset(offset)
                .limit(limit)
            )
        ).mappings()
        return [
            dict(row)
            | {
                "theme": row["theme"].value,
                "completed": row["total_stamps"] > 0
                and row["collected_stamps"] == row["total_stamps"],
            }
            for row in rows
        ]
