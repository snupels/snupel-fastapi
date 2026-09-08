from typing import Self

from pydantic import AnyHttpUrl, Field, model_validator

from app.schemas.common import Dto, TimestampedResponse


class BadgeCreate(Dto):
    rule_key: str | None = Field(default=None, min_length=1, max_length=50)
    image_url: AnyHttpUrl | None = None
    description: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def has_content(self) -> Self:
        if not self.image_url and not self.description:
            raise ValueError("image_url or description is required")
        return self


class BadgePatch(Dto):
    rule_key: str | None = Field(default=None, min_length=1, max_length=50)
    image_url: AnyHttpUrl | None = None
    description: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def not_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class BadgeResponse(TimestampedResponse):
    rule_key: str | None = Field(default=None, serialization_alias="ruleKey")
    image_url: str | None = Field(serialization_alias="imageUrl")
    description: str | None
