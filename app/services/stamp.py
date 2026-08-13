from app.repositories.stamp import StampRepository


class StampService:
    def __init__(self, repository: StampRepository) -> None:
        self.repository = repository

    async def seed_catalog(self) -> dict[str, int]:
        return await self.repository.seed_catalog()
