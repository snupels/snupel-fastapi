from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Passport


class PassportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, user_id: int) -> list[Passport]:
        return list(await self.session.scalars(select(Passport).where(Passport.user_id == user_id)))

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
