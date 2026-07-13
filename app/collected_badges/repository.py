from sqlalchemy.orm import Session

from app.collected import CollectedRepository
from app.models import Badge, CollectedBadge


class CollectedBadgeRepository(CollectedRepository):
    def __init__(self, session: Session) -> None:
        super().__init__(session, CollectedBadge, Badge, "badge_id")

