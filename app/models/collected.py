from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, func, select
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, column_property, mapped_column

from .activity import Stamp
from .base import Base


class CollectedStamp(Base):
    __tablename__ = "collected_stamps"
    __table_args__ = (
        UniqueConstraint("passport_id", "stamp_id", name="collected_stamps_passport_stamp_unique"),
        Index("collected_stamps_stamp_id_idx", "stamp_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    passport_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("passports.id", ondelete="CASCADE")
    )
    stamp_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("stamps.id", ondelete="CASCADE")
    )
    activity_id: Mapped[int] = column_property(
        select(Stamp.activity_id)
        .where(Stamp.id == stamp_id)
        .correlate_except(Stamp)
        .scalar_subquery()
    )
    collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class CollectedBadge(Base):
    __tablename__ = "collected_badges"
    __table_args__ = (
        UniqueConstraint("passport_id", "badge_id", name="collected_badges_passport_badge_unique"),
        Index("collected_badges_badge_id_idx", "badge_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    passport_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("passports.id", ondelete="CASCADE")
    )
    badge_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("badges.id", ondelete="CASCADE")
    )
    collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
