from datetime import datetime

from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin
from .enums import SubmissionStatus


class StampSubmission(TimestampMixin, Base):
    __tablename__ = "stamp_submissions"
    __table_args__ = (
        Index("stamp_submissions_passport_idx", "passport_id"),
        Index("stamp_submissions_status_idx", "status"),
        Index("stamp_submissions_feed_idx", "status", "share_to_feed", "reviewed_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    passport_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("passports.id", ondelete="CASCADE")
    )
    stamp_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("stamps.id", ondelete="CASCADE")
    )
    object_key: Mapped[str] = mapped_column(String(500))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    gps_accuracy_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime)
    share_to_feed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    feed_caption: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[SubmissionStatus] = mapped_column(
        SqlEnum(SubmissionStatus), default=SubmissionStatus.pending
    )
    reviewer_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
