from sqlalchemy.ext.asyncio import AsyncSession

from app.collected import CollectedRepository
from app.models import CollectedStamp, Stamp


class CollectedStampRepository(CollectedRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CollectedStamp, Stamp, "stamp_id")
