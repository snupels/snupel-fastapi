from datetime import datetime
from typing import Self

from pydantic import AnyHttpUrl, Field, model_validator

from app.dto import Dto, TimestampedResponse
from app.models import ActivityCategory


class ActivityCreate(Dto):
    category: ActivityCategory
    representative_image_url: AnyHttpUrl | None = None
    sport_name: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    place_name: str | None = Field(default=None, max_length=255)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class ActivityPatch(Dto):
    category: ActivityCategory | None = None
    representative_image_url: AnyHttpUrl | None = None
    sport_name: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    place_name: str | None = Field(default=None, max_length=255)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

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
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")

