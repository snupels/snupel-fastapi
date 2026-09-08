from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import AliasChoices, Field, field_validator

from app.models import RewardClaimStatus, RewardMilestone, SubmissionStatus
from app.schemas.activity import ActivityResponse
from app.schemas.common import Dto, OrmDto


class ActivityHistoryStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    collected = "collected"


class MeBadgeResponse(OrmDto):
    id: int = Field(gt=0)
    badge_id: int = Field(gt=0, serialization_alias="badgeId")
    rule_key: str | None = Field(serialization_alias="ruleKey")
    image_url: str | None = Field(serialization_alias="imageUrl")
    description: str | None
    collected_at: datetime = Field(serialization_alias="collectedAt")


class SavedActivityResponse(OrmDto):
    id: int = Field(gt=0)
    activity_id: int = Field(gt=0, serialization_alias="activityId")
    created_at: datetime = Field(serialization_alias="createdAt")
    activity: ActivityResponse


class ActivityHistoryResponse(OrmDto):
    id: int = Field(gt=0)
    type: Literal["submission", "stamp", "saved"]
    status: SubmissionStatus | Literal["collected"]
    activity_id: int = Field(gt=0, serialization_alias="activityId")
    course_id: int | None = Field(serialization_alias="courseId")
    submission_id: int | None = Field(serialization_alias="submissionId")
    title: str | None
    place_name: str | None = Field(serialization_alias="placeName")
    sigun: str | None
    image_url: str | None = Field(serialization_alias="imageUrl")
    occurred_at: datetime = Field(serialization_alias="occurredAt")
    rejection_reason: str | None = Field(serialization_alias="rejectionReason")


class RewardClaimCreate(Dto):
    recipient_name: str = Field(
        min_length=1,
        max_length=100,
        validation_alias=AliasChoices("recipientName", "recipient_name"),
    )
    phone_number: str = Field(
        min_length=7,
        max_length=30,
        validation_alias=AliasChoices("phoneNumber", "phone_number"),
    )
    address: str = Field(min_length=1, max_length=1000)

    @field_validator("recipient_name", "phone_number", "address")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be blank")
        return value


class RewardClaimPatch(Dto):
    status: RewardClaimStatus


class RewardClaimResponse(OrmDto):
    id: int | None = Field(default=None, gt=0)
    user_id: int = Field(gt=0, serialization_alias="userId")
    milestone: RewardMilestone
    recipient_name: str | None = Field(default=None, serialization_alias="recipientName")
    phone_number: str | None = Field(default=None, serialization_alias="phoneNumber")
    address: str | None = None
    status: RewardClaimStatus
    requested_at: datetime | None = Field(default=None, serialization_alias="requestedAt")
    fulfilled_at: datetime | None = Field(default=None, serialization_alias="fulfilledAt")
