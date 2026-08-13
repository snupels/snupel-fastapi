from typing import Self

from pydantic import AnyHttpUrl, Field, model_validator

from app.models import ActivityCategory, CourseTheme
from app.schemas.common import Dto, TimestampedResponse


class CourseCreate(Dto):
    category: ActivityCategory = ActivityCategory.tour
    sport_name: str | None = Field(default=None, max_length=100)
    recommended_companion: str | None = Field(default=None, max_length=100)
    representative_image_url: AnyHttpUrl | None = None
    estimated_duration_minutes: int | None = Field(default=None, gt=0)
    theme: CourseTheme
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    is_published: bool = False

    @model_validator(mode="after")
    def sport_category(self) -> Self:
        if self.category == ActivityCategory.sports and not self.sport_name:
            raise ValueError("sport_name is required for sports courses")
        if self.category != ActivityCategory.sports and self.sport_name is not None:
            raise ValueError("sport_name is only allowed for sports courses")
        return self


class CoursePatch(Dto):
    category: ActivityCategory | None = None
    sport_name: str | None = Field(default=None, max_length=100)
    recommended_companion: str | None = Field(default=None, max_length=100)
    representative_image_url: AnyHttpUrl | None = None
    estimated_duration_minutes: int | None = Field(default=None, gt=0)
    theme: CourseTheme | None = None
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    is_published: bool | None = None

    @model_validator(mode="after")
    def not_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class CourseResponse(TimestampedResponse):
    category: ActivityCategory
    sport_name: str | None = Field(serialization_alias="sportName")
    recommended_companion: str | None = Field(serialization_alias="recommendedCompanion")
    representative_image_url: str | None = Field(serialization_alias="representativeImageUrl")
    estimated_duration_minutes: int | None = Field(serialization_alias="estimatedDurationMinutes")
    theme: CourseTheme
    title: str | None = None
    description: str | None = None
    is_published: bool = Field(default=False, serialization_alias="isPublished")


class CourseItineraryStop(Dto):
    position: int = Field(ge=0)
    stamp_id: int = Field(gt=0, serialization_alias="stampId")
    activity_id: int = Field(gt=0, serialization_alias="activityId")
    category: ActivityCategory
    place_name: str | None = Field(serialization_alias="placeName")
    sport_name: str | None = Field(serialization_alias="sportName")
    address: str | None
    latitude: float | None
    longitude: float | None
    estimated_minutes: int = Field(gt=0, serialization_alias="estimatedMinutes")


class CourseItineraryResponse(Dto):
    id: int = Field(gt=0)
    title: str | None
    description: str | None
    category: ActivityCategory
    sport_name: str | None = Field(serialization_alias="sportName")
    theme: CourseTheme
    recommended_companion: str | None = Field(serialization_alias="recommendedCompanion")
    estimated_duration_minutes: int = Field(ge=0, serialization_alias="estimatedDurationMinutes")
    stops: list[CourseItineraryStop]
