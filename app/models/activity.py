from decimal import Decimal

from sqlalchemy import Enum as SqlEnum, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin
from .enums import ActivityCategory


class Activity(TimestampMixin, Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    category: Mapped[ActivityCategory] = mapped_column(SqlEnum(ActivityCategory))
    representative_image_url: Mapped[str | None] = mapped_column(Text)
    sport_name: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    place_name: Mapped[str | None] = mapped_column(String(255))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))


class Stamp(TimestampMixin, Base):
    __tablename__ = "stamps"
    __table_args__ = (Index("stamps_activity_id_idx", "activity_id"),)

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("activities.id", ondelete="CASCADE")
    )
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
