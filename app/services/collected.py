from sqlalchemy.exc import IntegrityError

from app.deps.auth import LoginUser
from app.exceptions import ApiError
from app.repositories.collected import CollectedRepository


class CollectedService:
    def __init__(self, repository: CollectedRepository, noun: str) -> None:
        self.repository = repository
        self.noun = noun

    @staticmethod
    def _user(user: LoginUser | None) -> LoginUser:
        if not user:
            raise ApiError(401, "unauthorized", "Login is required.")
        return user

    async def _found(self, item_id: int, user: LoginUser):
        row = await self.repository.get(item_id, user.id)
        if not row:
            raise ApiError(404, "not_found", f"Collected {self.noun.lower()} not found.")
        return row

    async def _valid(
        self, passport_id: int, target_id: int, owner_id: int, except_id: int = 0
    ):
        if not await self.repository.passport_owned(passport_id, owner_id):
            raise ApiError(404, "not_found", "Passport not found.")
        if not await self.repository.target_exists(target_id):
            raise ApiError(404, "not_found", f"{self.noun} not found.")
        if await self.repository.duplicate(passport_id, target_id, except_id):
            raise ApiError(409, "conflict", f"{self.noun} already collected.")

    async def list(self, user: LoginUser | None):
        return await self.repository.list(self._user(user).id)

    async def get(self, item_id: int, user: LoginUser | None):
        return await self._found(item_id, self._user(user))

    async def create(self, body, user: LoginUser | None):
        actor = self._user(user)
        target_id = getattr(body, self.repository.target_field)
        await self._valid(body.passport_id, target_id, actor.id)
        try:
            return await self.repository.create(body.passport_id, target_id)
        except IntegrityError as error:
            raise ApiError(409, "conflict", f"{self.noun} already collected.") from error

    async def update(self, item_id: int, body, user: LoginUser | None):
        actor = self._user(user)
        row = await self._found(item_id, actor)
        passport_id = body.passport_id if "passport_id" in body.model_fields_set else row.passport_id
        target_id = (
            getattr(body, self.repository.target_field)
            if self.repository.target_field in body.model_fields_set
            else getattr(row, self.repository.target_field)
        )
        await self._valid(passport_id, target_id, actor.id, item_id)
        try:
            return await self.repository.update(row, passport_id, target_id)
        except IntegrityError as error:
            raise ApiError(409, "conflict", f"{self.noun} already collected.") from error

    async def remove(self, item_id: int, user: LoginUser | None) -> None:
        await self.repository.remove(await self._found(item_id, self._user(user)))
