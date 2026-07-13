from typing import Self

from pydantic import AnyHttpUrl, Field, model_validator

from app.dto import Dto, TimestampedResponse


class BadgeCreate(Dto):
    image_url: AnyHttpUrl | None = None
    description: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def has_content(self) -> Self:
        if not self.image_url and not self.description:
            raise ValueError("image_url or description is required")
        return self


class BadgePatch(Dto):
    image_url: AnyHttpUrl | None = None
    description: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def not_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class BadgeResponse(TimestampedResponse):
    image_url: str | None = Field(serialization_alias="imageUrl")
    description: str | None

