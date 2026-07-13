from .errors import ApiError


class CrudService:
    def __init__(self, repository, name: str) -> None:
        self.repository = repository
        self.name = name

    async def list(self, _user=None):
        return await self.repository.list()

    async def get(self, item_id: int, _user=None):
        row = await self.repository.get(item_id)
        if not row:
            raise ApiError(404, "not_found", f"{self.name} not found.")
        return row

    async def create(self, body, _user=None):
        return await self.repository.create(body)

    async def update(self, item_id: int, body, user=None):
        return await self.repository.update(await self.get(item_id, user), body)

    async def remove(self, item_id: int, user=None) -> None:
        await self.repository.remove(await self.get(item_id, user))
