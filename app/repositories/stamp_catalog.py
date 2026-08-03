from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StampCatalog
from app.repositories.base import CrudRepository


class StampCatalogRepository(CrudRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, StampCatalog, None)
