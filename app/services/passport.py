from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.deps.auth import LoginUser
from app.exceptions import ApiError
from app.repositories.passport import PassportRepository


class PassportService:
    def __init__(self, repository: PassportRepository) -> None:
        self.repository = repository

    @staticmethod
    def _user(user: LoginUser | None) -> LoginUser:
        if not user:
            raise ApiError(401, "unauthorized", "Login is required.")
        return user

    async def _found(self, item_id: int, user: LoginUser):
        row = await self.repository.get(item_id, user.id)
        if not row:
            raise ApiError(404, "not_found", "Passport not found.")
        return row

    async def list(self, user: LoginUser | None):
        return await self.repository.list(self._user(user).id)

    async def get(self, item_id: int, user: LoginUser | None):
        return await self._found(item_id, self._user(user))

    async def create(self, body, user: LoginUser | None):
        actor = self._user(user)
        if body.user_id != actor.id:
            raise ApiError(403, "forbidden", "A passport can only belong to you.")
        if await self.repository.get_by_user(actor.id):
            raise ApiError(409, "conflict", "Passport already exists.")
        try:
            return await self.repository.create(actor.id)
        except IntegrityError as error:
            raise ApiError(409, "conflict", "Passport already exists.") from error

    async def update(self, item_id: int, body, user: LoginUser | None):
        actor = self._user(user)
        if body.user_id != actor.id:
            raise ApiError(403, "forbidden", "A passport can only belong to you.")
        return await self._found(item_id, actor)

    async def remove(self, item_id: int, user: LoginUser | None) -> None:
        await self.repository.remove(await self._found(item_id, self._user(user)))

    async def missions(self, item_id: int, user: LoginUser | None):
        passport = await self._found(item_id, self._user(user))
        return await self.repository.mission_progress(passport.id)


def get_passport_service(session: AsyncSession = Depends(get_session)) -> PassportService:
    return PassportService(PassportRepository(session))
