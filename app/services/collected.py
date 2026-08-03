from sqlalchemy.exc import IntegrityError

from app.exceptions import ApiError
from app.repositories.collected import CollectedRepository


class CollectedService:
    def __init__(self, repository: CollectedRepository, noun: str) -> None:
        self.repository = repository
        self.noun = noun

    async def _found(self, item_id: int):
        row = await self.repository.get(item_id)
        if not row:
            raise ApiError(404, "not_found", f"Collected {self.noun.lower()} not found.")
        return row

    async def _valid(self, passport_id: int, target_id: int, except_id: int = 0):
        if not await self.repository.passport_exists(passport_id):
            raise ApiError(404, "not_found", "Passport not found.")
        if not await self.repository.target_exists(target_id):
            raise ApiError(404, "not_found", f"{self.noun} not found.")
        if await self.repository.duplicate(passport_id, target_id, except_id):
            raise ApiError(409, "conflict", f"{self.noun} already collected.")

    async def list(self, _user=None, *, offset: int = 0, limit: int = 20):
        return await self.repository.list(offset=offset, limit=limit)

    async def get(self, item_id: int, _user=None):
        return await self._found(item_id)

    async def create(self, body, _user=None):
        target_id = getattr(body, self.repository.target_field)
        await self._valid(body.passport_id, target_id)
        try:
            return await self.repository.create(body.passport_id, target_id)
        except IntegrityError as error:
            raise ApiError(409, "conflict", f"{self.noun} already collected.") from error

    async def update(self, item_id: int, body, _user=None):
        row = await self._found(item_id)
        passport_id = body.passport_id if "passport_id" in body.model_fields_set else row.passport_id
        target_id = (
            getattr(body, self.repository.target_field)
            if self.repository.target_field in body.model_fields_set
            else getattr(row, self.repository.target_field)
        )
        await self._valid(passport_id, target_id, item_id)
        try:
            return await self.repository.update(row, passport_id, target_id)
        except IntegrityError as error:
            raise ApiError(409, "conflict", f"{self.noun} already collected.") from error

    async def remove(self, item_id: int, _user=None) -> None:
        await self.repository.remove(await self._found(item_id))
