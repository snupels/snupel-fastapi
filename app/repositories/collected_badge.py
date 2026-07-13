from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Badge, CollectedBadge
from app.repositories.collected import CollectedRepository


class CollectedBadgeRepository(CollectedRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CollectedBadge, Badge, "badge_id")
