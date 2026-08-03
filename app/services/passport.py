from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.exceptions import ApiError
from app.repositories.passport import PassportRepository


class PassportService:
    def __init__(self, repository: PassportRepository) -> None:
        self.repository = repository

    async def _found(self, item_id: int):
        row = await self.repository.get(item_id)
        if not row:
            raise ApiError(404, "not_found", "Passport not found.")
        return row

    async def list(self, _user=None, *, offset: int = 0, limit: int = 20):
        return await self.repository.list(offset=offset, limit=limit)

    async def get(self, item_id: int, _user=None):
        return await self._found(item_id)

    async def create(self, body, _user=None):
        if await self.repository.get_by_user(body.user_id):
            raise ApiError(409, "conflict", "Passport already exists.")
        try:
            return await self.repository.create(body.user_id)
        except IntegrityError as error:
            raise ApiError(409, "conflict", "Passport already exists.") from error

    async def update(self, item_id: int, body, _user=None):
        row = await self._found(item_id)
        existing = await self.repository.get_by_user(body.user_id)
        if existing and existing.id != item_id:
            raise ApiError(409, "conflict", "Passport already exists.")
        return await self.repository.update(row, body.user_id)

    async def remove(self, item_id: int, _user=None) -> None:
        await self.repository.remove(await self._found(item_id))

    async def missions(
        self,
        item_id: int,
        _user=None,
        *,
        offset: int = 0,
        limit: int = 20,
    ):
        passport = await self._found(item_id)
        return await self.repository.mission_progress(
            passport.id, offset=offset, limit=limit
        )


def get_passport_service(session: AsyncSession = Depends(get_session)) -> PassportService:
    return PassportService(PassportRepository(session))
