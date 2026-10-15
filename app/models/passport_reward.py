from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TeeClaimStatus(str, Enum):
    requested = "requested"
    preparing = "preparing"
    shipped = "shipped"
    completed = "completed"


class PassportRewardCampaign(Base):
    __tablename__ = "passport_reward_campaigns"
    __table_args__ = (
        CheckConstraint(
            "claimed_count >= 0 AND claimed_count <= quantity", name="tee_campaign_capacity"
        ),
    )
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    required_stamps: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    claimed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


class PassportTeeClaim(Base):
    __tablename__ = "passport_tee_claims"
    __table_args__ = (
        UniqueConstraint("campaign_id", "user_id", name="tee_claim_member_unique"),
        UniqueConstraint("campaign_id", "allocation_no", name="tee_claim_slot_unique"),
        Index("tee_claim_status_idx", "status", "requested_at"),
    )
    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    campaign_id: Mapped[str] = mapped_column(String(50), ForeignKey("passport_reward_campaigns.id"))
    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    allocation_no: Mapped[int] = mapped_column(Integer)
    size: Mapped[str] = mapped_column(String(5))
    recipient_name: Mapped[str] = mapped_column(String(100))
    phone_number: Mapped[str] = mapped_column(String(11))
    postal_code: Mapped[str] = mapped_column(String(5))
    address: Mapped[str] = mapped_column(String(500))
    address_detail: Mapped[str] = mapped_column(String(200), default="", server_default="")
    status: Mapped[TeeClaimStatus] = mapped_column(
        SqlEnum(TeeClaimStatus), default=TeeClaimStatus.requested, server_default="requested"
    )
    consent_version: Mapped[str] = mapped_column(String(50))
    consented_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime)
