from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class CrudRepository:
    def __init__(self, session: AsyncSession, model: type, values) -> None:
        self.session = session
        self.model = model
        self.values = values

    async def list(self) -> list:
        return list(await self.session.scalars(select(self.model).order_by(self.model.id)))

    async def get(self, item_id: int):
        return await self.session.get(self.model, item_id)

    async def create(self, body):
        row = self.model(**self.values(body))
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def update(self, row, body):
        for key, value in self.values(body).items():
            setattr(row, key, value)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def remove(self, row) -> None:
        await self.session.delete(row)
        await self.session.flush()


def dumped(body) -> dict[str, Any]:
    return body.model_dump(exclude_unset=True)
