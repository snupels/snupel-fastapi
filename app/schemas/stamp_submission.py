from datetime import datetime

from pydantic import AliasChoices, Field, field_validator

from app.models import ActivityCategory, SubmissionStatus
from app.schemas.common import Dto, OrmDto, TimestampedResponse


class UploadUrlRequest(Dto):
    passport_id: int = Field(
        gt=0, validation_alias=AliasChoices("passportId", "passport_id")
    )
    stamp_id: int = Field(gt=0, validation_alias=AliasChoices("stampId", "stamp_id"))
    content_type: str = Field(
        validation_alias=AliasChoices("contentType", "content_type")
    )


class UploadUrlResponse(Dto):
    upload_url: str = Field(serialization_alias="uploadUrl")
    fields: dict[str, str]
    object_key: str = Field(serialization_alias="objectKey")
    expires_in: int = Field(serialization_alias="expiresIn")


class StampSubmissionCreate(Dto):
    passport_id: int = Field(
        gt=0, validation_alias=AliasChoices("passportId", "passport_id")
    )
    stamp_id: int = Field(gt=0, validation_alias=AliasChoices("stampId", "stamp_id"))
    object_key: str = Field(
        min_length=1,
        max_length=500,
        validation_alias=AliasChoices("objectKey", "object_key"),
    )


class StampSubmissionResponse(TimestampedResponse):
    passport_id: int = Field(serialization_alias="passportId")
    stamp_id: int = Field(serialization_alias="stampId")
    object_key: str = Field(serialization_alias="objectKey")
    status: SubmissionStatus
    reviewer_id: int | None = Field(serialization_alias="reviewerId")
    reviewed_at: datetime | None = Field(serialization_alias="reviewedAt")
    rejection_reason: str | None = Field(serialization_alias="rejectionReason")
    proof_url: str | None = Field(default=None, serialization_alias="proofUrl")


class SubmissionActivityResponse(OrmDto):
    id: int = Field(gt=0)
    category: ActivityCategory
    place_name: str | None = Field(serialization_alias="placeName")
    address: str | None
    starts_at: datetime | None = Field(serialization_alias="startsAt")
    ends_at: datetime | None = Field(serialization_alias="endsAt")


class AdminStampSubmissionResponse(StampSubmissionResponse):
    activity: SubmissionActivityResponse


class RejectSubmission(Dto):
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason cannot be blank")
        return value
