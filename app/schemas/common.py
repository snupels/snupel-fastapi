from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Dto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrmDto(BaseModel):
    model_config = ConfigDict(from_attributes=True, serialize_by_alias=True)


class TimestampedResponse(OrmDto):
    id: int = Field(gt=0)
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")


class ErrorResponse(BaseModel):
    error: str
    message: str


class Pagination(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size
