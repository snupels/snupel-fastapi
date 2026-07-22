from datetime import datetime

from pydantic import Field

from app.models import SubmissionStatus
from app.schemas.common import Dto, TimestampedResponse


class UploadUrlRequest(Dto):
    passport_id: int = Field(gt=0)
    stamp_id: int = Field(gt=0)
    content_type: str


class UploadUrlResponse(Dto):
    upload_url: str = Field(serialization_alias="uploadUrl")
    fields: dict[str, str]
    object_key: str = Field(serialization_alias="objectKey")
    expires_in: int = Field(serialization_alias="expiresIn")


class StampSubmissionCreate(Dto):
    passport_id: int = Field(gt=0)
    stamp_id: int = Field(gt=0)
    object_key: str = Field(min_length=1, max_length=500)


class StampSubmissionResponse(TimestampedResponse):
    passport_id: int = Field(serialization_alias="passportId")
    stamp_id: int = Field(serialization_alias="stampId")
    object_key: str = Field(serialization_alias="objectKey")
    status: SubmissionStatus
    reviewer_id: int | None = Field(serialization_alias="reviewerId")
    reviewed_at: datetime | None = Field(serialization_alias="reviewedAt")
    rejection_reason: str | None = Field(serialization_alias="rejectionReason")
    proof_url: str | None = Field(default=None, serialization_alias="proofUrl")


class RejectSubmission(Dto):
    reason: str = Field(min_length=1, max_length=1000)
