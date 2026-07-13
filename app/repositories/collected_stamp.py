from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CollectedStamp, Stamp
from app.repositories.collected import CollectedRepository


class CollectedStampRepository(CollectedRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CollectedStamp, Stamp, "stamp_id")
