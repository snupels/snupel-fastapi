from sqlalchemy import select

from app.models import Passport


class CollectedRepository:
    def __init__(self, session, model, target_model, target_field: str) -> None:
        self.session = session
        self.model = model
        self.target_model = target_model
        self.target_field = target_field

    async def list(self, user_id: int, *, offset: int = 0, limit: int = 20) -> list:
        statement = (
            select(self.model)
            .join(Passport, self.model.passport_id == Passport.id)
            .where(Passport.user_id == user_id)
            .order_by(self.model.id)
            .offset(offset)
            .limit(limit)
        )
        return list(await self.session.scalars(statement))

    async def get(self, item_id: int, user_id: int):
        return await self.session.scalar(
            select(self.model)
            .join(Passport, self.model.passport_id == Passport.id)
            .where(self.model.id == item_id, Passport.user_id == user_id)
        )

    async def passport_owned(self, passport_id: int, user_id: int) -> bool:
        return await self.session.scalar(
            select(Passport.id).where(Passport.id == passport_id, Passport.user_id == user_id)
        ) is not None

    async def target_exists(self, target_id: int) -> bool:
        return await self.session.get(self.target_model, target_id) is not None

    async def duplicate(self, passport_id: int, target_id: int, except_id: int = 0) -> bool:
        target = getattr(self.model, self.target_field)
        return await self.session.scalar(
            select(self.model.id).where(
                self.model.passport_id == passport_id,
                target == target_id,
                self.model.id != except_id,
            )
        ) is not None

    async def create(self, passport_id: int, target_id: int):
        row = self.model(passport_id=passport_id, **{self.target_field: target_id})
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def update(self, row, passport_id: int, target_id: int):
        row.passport_id = passport_id
        setattr(row, self.target_field, target_id)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def remove(self, row) -> None:
        await self.session.delete(row)
        await self.session.flush()
