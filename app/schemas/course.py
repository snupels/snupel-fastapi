from typing import Self

from pydantic import AnyHttpUrl, Field, model_validator

from app.models import CourseTheme
from app.schemas.common import Dto, TimestampedResponse


class CourseCreate(Dto):
    recommended_companion: str | None = Field(default=None, max_length=100)
    representative_image_url: AnyHttpUrl | None = None
    estimated_duration_minutes: int | None = Field(default=None, gt=0)
    theme: CourseTheme
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    is_published: bool = False


class CoursePatch(Dto):
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
    recommended_companion: str | None = Field(serialization_alias="recommendedCompanion")
    representative_image_url: str | None = Field(serialization_alias="representativeImageUrl")
    estimated_duration_minutes: int | None = Field(serialization_alias="estimatedDurationMinutes")
    theme: CourseTheme
    title: str | None = None
    description: str | None = None
    is_published: bool = Field(default=False, serialization_alias="isPublished")
