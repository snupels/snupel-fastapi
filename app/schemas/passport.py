from pydantic import Field

from app.schemas.common import Dto, TimestampedResponse


class PassportCreate(Dto):
    user_id: int = Field(gt=0)


class PassportPatch(PassportCreate):
    pass


class PassportResponse(TimestampedResponse):
    user_id: int = Field(gt=0, serialization_alias="userId")


class MissionProgress(Dto):
    course_id: int = Field(gt=0, serialization_alias="courseId")
    title: str | None
    theme: str
    total_stamps: int = Field(ge=0, serialization_alias="totalStamps")
    collected_stamps: int = Field(ge=0, serialization_alias="collectedStamps")
    completed: bool
