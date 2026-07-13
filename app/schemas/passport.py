from pydantic import Field

from app.schemas.common import Dto, TimestampedResponse


class PassportCreate(Dto):
    user_id: int = Field(gt=0)


class PassportPatch(PassportCreate):
    pass


class PassportResponse(TimestampedResponse):
    user_id: int = Field(gt=0, serialization_alias="userId")
