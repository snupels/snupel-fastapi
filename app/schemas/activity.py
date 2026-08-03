from datetime import datetime
from typing import Any
from typing import Self

from pydantic import AnyHttpUrl, Field, model_validator

from app.models import ActivityCategory
from app.schemas.common import Dto, OrmDto, TimestampedResponse


class ActivityCreate(Dto):
    category: ActivityCategory
    representative_image_url: AnyHttpUrl | None = None
    sport_name: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    place_name: str | None = Field(default=None, max_length=255)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    source: str | None = Field(default=None, max_length=50)
    external_id: str | None = Field(default=None, max_length=100)
    summary: str | None = None
    address: str | None = Field(default=None, max_length=500)
    source_url: AnyHttpUrl | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    metadata: dict[str, Any] | None = None
    last_synced_at: datetime | None = None
    is_active: bool = True


class ActivityPatch(Dto):
    category: ActivityCategory | None = None
    representative_image_url: AnyHttpUrl | None = None
    sport_name: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    place_name: str | None = Field(default=None, max_length=255)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    source: str | None = Field(default=None, max_length=50)
    external_id: str | None = Field(default=None, max_length=100)
    summary: str | None = None
    address: str | None = Field(default=None, max_length=500)
    source_url: AnyHttpUrl | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    metadata: dict[str, Any] | None = None
    last_synced_at: datetime | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def not_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class ActivityResponse(TimestampedResponse):
    category: ActivityCategory
    representative_image_url: str | None = Field(serialization_alias="representativeImageUrl")
    sport_name: str | None = Field(serialization_alias="sportName")
    region: str | None
    place_name: str | None = Field(serialization_alias="placeName")
    latitude: float | None
    longitude: float | None
    source: str | None = None
    external_id: str | None = Field(default=None, serialization_alias="externalId")
    summary: str | None = None
    address: str | None = None
    source_url: str | None = Field(default=None, serialization_alias="sourceUrl")
    starts_at: datetime | None = Field(default=None, serialization_alias="startsAt")
    ends_at: datetime | None = Field(default=None, serialization_alias="endsAt")
    source_metadata: dict[str, Any] | None = Field(default=None, serialization_alias="metadata")
    last_synced_at: datetime | None = Field(default=None, serialization_alias="lastSyncedAt")
    is_active: bool = Field(default=True, serialization_alias="isActive")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")


class ActivityExploreResponse(ActivityResponse):
    themes: list[str]
    has_mission: bool = Field(serialization_alias="hasMission")


class ActivityMapResponse(OrmDto):
    id: int = Field(gt=0)
    category: ActivityCategory
    place_name: str | None = Field(serialization_alias="placeName")
    sport_name: str | None = Field(serialization_alias="sportName")
    latitude: float
    longitude: float
    has_mission: bool = Field(serialization_alias="hasMission")
