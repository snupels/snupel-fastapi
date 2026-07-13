from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Badge
from app.repository import CrudRepository, dumped


class BadgeRepository(CrudRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Badge, self._values)

    @staticmethod
    def _values(body):
        values = dumped(body)
        if values.get("image_url") is not None:
            values["image_url"] = str(values["image_url"])
        return values
