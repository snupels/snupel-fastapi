from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
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


class FeedLike(TimestampMixin, Base):
    __tablename__ = "feed_likes"
    __table_args__ = (
        UniqueConstraint("submission_id", "user_id", name="feed_likes_submission_user_unique"),
        Index("feed_likes_submission_idx", "submission_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("stamp_submissions.id", ondelete="CASCADE")
    )
    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="CASCADE")
    )


class FeedComment(TimestampMixin, Base):
    __tablename__ = "feed_comments"
    __table_args__ = (Index("feed_comments_submission_idx", "submission_id", "created_at"),)

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("stamp_submissions.id", ondelete="CASCADE")
    )
    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    content: Mapped[str] = mapped_column(String(500))
