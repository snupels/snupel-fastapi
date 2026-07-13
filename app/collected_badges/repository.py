from sqlalchemy.ext.asyncio import AsyncSession

from app.collected import CollectedRepository
from app.models import Badge, CollectedBadge


class CollectedBadgeRepository(CollectedRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CollectedBadge, Badge, "badge_id")
