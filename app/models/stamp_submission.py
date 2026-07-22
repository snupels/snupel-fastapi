from datetime import datetime

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin
from .enums import SubmissionStatus


class StampSubmission(TimestampMixin, Base):
    __tablename__ = "stamp_submissions"
    __table_args__ = (
        Index("stamp_submissions_passport_idx", "passport_id"),
        Index("stamp_submissions_status_idx", "status"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    passport_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("passports.id", ondelete="CASCADE")
    )
    stamp_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("stamps.id", ondelete="CASCADE")
    )
    object_key: Mapped[str] = mapped_column(String(500))
    status: Mapped[SubmissionStatus] = mapped_column(
        SqlEnum(SubmissionStatus), default=SubmissionStatus.pending
    )
    reviewer_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
