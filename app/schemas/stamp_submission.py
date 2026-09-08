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
    share_to_feed: bool = Field(
        default=False,
        validation_alias=AliasChoices("shareToFeed", "share_to_feed"),
    )
    feed_caption: str | None = Field(
        default=None,
        max_length=300,
        validation_alias=AliasChoices("feedCaption", "feed_caption"),
    )

    @field_validator("feed_caption")
    @classmethod
    def strip_caption(cls, value: str | None) -> str | None:
        value = value.strip() if value is not None else None
        return value or None


class StampSubmissionResponse(TimestampedResponse):
    passport_id: int = Field(serialization_alias="passportId")
    stamp_id: int = Field(serialization_alias="stampId")
    object_key: str = Field(serialization_alias="objectKey")
    status: SubmissionStatus
    reviewer_id: int | None = Field(serialization_alias="reviewerId")
    reviewed_at: datetime | None = Field(serialization_alias="reviewedAt")
    rejection_reason: str | None = Field(serialization_alias="rejectionReason")
    proof_url: str | None = Field(default=None, serialization_alias="proofUrl")
    share_to_feed: bool = Field(default=False, serialization_alias="shareToFeed")
    feed_caption: str | None = Field(default=None, serialization_alias="feedCaption")
    activity: "SubmissionActivityResponse | None" = None
    course_title: str | None = Field(default=None, serialization_alias="courseTitle")
    stamp_name: str | None = Field(default=None, serialization_alias="stampName")
    submitted_at: datetime | None = Field(default=None, serialization_alias="submittedAt")


class SubmissionActivityResponse(OrmDto):
    id: int = Field(gt=0)
    category: ActivityCategory
    place_name: str | None = Field(serialization_alias="placeName")
    sport_name: str | None = Field(default=None, serialization_alias="sportName")
    sigun: str | None = None
    representative_image_url: str | None = Field(
        default=None, serialization_alias="representativeImageUrl"
    )
    address: str | None
    starts_at: datetime | None = Field(serialization_alias="startsAt")
    ends_at: datetime | None = Field(serialization_alias="endsAt")


class AdminStampSubmissionResponse(StampSubmissionResponse):
    activity: SubmissionActivityResponse


class FeedVisibilityUpdate(Dto):
    share_to_feed: bool = Field(
        validation_alias=AliasChoices("shareToFeed", "share_to_feed")
    )
    feed_caption: str | None = Field(
        default=None,
        max_length=300,
        validation_alias=AliasChoices("feedCaption", "feed_caption"),
    )

    @field_validator("feed_caption")
    @classmethod
    def strip_caption(cls, value: str | None) -> str | None:
        value = value.strip() if value is not None else None
        return value or None


class CommunityFeedResponse(OrmDto):
    is_demo: bool = Field(default=False, serialization_alias="isDemo")
    id: int = Field(gt=0)
    proof_url: str | None = Field(serialization_alias="proofUrl")
    caption: str | None
    author_id: int = Field(gt=0, serialization_alias="authorId")
    author_name: str = Field(serialization_alias="authorName")
    author_profile_image_url: str | None = Field(
        default=None, serialization_alias="authorProfileImageUrl"
    )
    place_name: str | None = Field(serialization_alias="placeName")
    sigun: str | None
    sport_name: str | None = Field(serialization_alias="sportName")
    approved_at: datetime = Field(serialization_alias="approvedAt")
    like_count: int = Field(default=0, ge=0, serialization_alias="likeCount")
    comment_count: int = Field(default=0, ge=0, serialization_alias="commentCount")
    liked_by_me: bool = Field(default=False, serialization_alias="likedByMe")


class FeedCommentCreate(Dto):
    content: str = Field(min_length=1, max_length=500)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("comment cannot be blank")
        return value


class FeedCommentResponse(OrmDto):
    id: int = Field(gt=0)
    author_id: int = Field(gt=0, serialization_alias="authorId")
    author_name: str = Field(serialization_alias="authorName")
    author_profile_image_url: str | None = Field(
        default=None, serialization_alias="authorProfileImageUrl"
    )
    content: str
    created_at: datetime = Field(serialization_alias="createdAt")


class FeedEngagementResponse(OrmDto):
    like_count: int = Field(ge=0, serialization_alias="likeCount")
    liked_by_me: bool = Field(serialization_alias="likedByMe")


class RejectSubmission(Dto):
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason cannot be blank")
        return value
