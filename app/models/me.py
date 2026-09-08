from datetime import datetime

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin
from .enums import RewardClaimStatus, RewardMilestone


class SavedActivity(TimestampMixin, Base):
    __tablename__ = "saved_activities"
    __table_args__ = (
        UniqueConstraint("user_id", "activity_id", name="saved_activities_user_activity_unique"),
        Index("saved_activities_activity_id_idx", "activity_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    activity_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("activities.id", ondelete="CASCADE")
    )


class RewardClaim(Base):
    __tablename__ = "reward_claims"
    __table_args__ = (
        UniqueConstraint("user_id", "milestone", name="reward_claims_user_milestone_unique"),
        Index("reward_claims_status_idx", "status"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    milestone: Mapped[RewardMilestone] = mapped_column(SqlEnum(RewardMilestone))
    recipient_name: Mapped[str] = mapped_column(String(100))
    phone_number: Mapped[str] = mapped_column(String(30))
    address: Mapped[str] = mapped_column(Text)
    status: Mapped[RewardClaimStatus] = mapped_column(
        SqlEnum(RewardClaimStatus),
        default=RewardClaimStatus.requested,
        server_default=RewardClaimStatus.requested.value,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime)
