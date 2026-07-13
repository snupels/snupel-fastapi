from datetime import datetime
from typing import Self

from pydantic import Field, model_validator

from app.schemas.common import Dto, OrmDto


class CollectedStampCreate(Dto):
    passport_id: int = Field(gt=0)
    stamp_id: int = Field(gt=0)


class CollectedStampPatch(Dto):
    passport_id: int | None = Field(default=None, gt=0)
    stamp_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def not_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class CollectedStampResponse(OrmDto):
    id: int = Field(gt=0)
    passport_id: int = Field(gt=0, serialization_alias="passportId")
    stamp_id: int = Field(gt=0, serialization_alias="stampId")
    collected_at: datetime = Field(serialization_alias="collectedAt")
