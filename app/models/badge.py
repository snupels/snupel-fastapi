from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Badge(TimestampMixin, Base):
    __tablename__ = "badges"
    __table_args__ = (UniqueConstraint("rule_key", name="badges_rule_key_unique"),)

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    rule_key: Mapped[str | None] = mapped_column(String(50))
    image_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
