from decimal import Decimal

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, ForeignKey, Index, JSON, Numeric, String, Text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin
from .enums import ActivityCategory


class Activity(TimestampMixin, Base):
    __tablename__ = "activities"
    __table_args__ = (
        Index("activities_source_external_unique", "source", "external_id", unique=True),
        Index("activities_source_synced_idx", "source", "last_synced_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    category: Mapped[ActivityCategory] = mapped_column(SqlEnum(ActivityCategory))
    representative_image_url: Mapped[str | None] = mapped_column(Text)
    sport_name: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    place_name: Mapped[str | None] = mapped_column(String(255))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    source: Mapped[str | None] = mapped_column(String(50))
    external_id: Mapped[str | None] = mapped_column(String(100))
    summary: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    source_metadata: Mapped[dict | None] = mapped_column("metadata", JSON)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


class Stamp(TimestampMixin, Base):
    __tablename__ = "stamps"
    __table_args__ = (Index("stamps_activity_id_idx", "activity_id"),)

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("activities.id", ondelete="CASCADE")
    )
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
