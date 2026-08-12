from pydantic import Field

from app.models import CourseTheme
from app.schemas.common import Dto


class CourseRecommendationRequest(Dto):
    theme: CourseTheme
    region: str = Field(min_length=1, max_length=100)
    sport: str | None = Field(default=None, max_length=100)
    available_minutes: int = Field(
        gt=0, le=1440, validation_alias="availableMinutes", serialization_alias="availableMinutes"
    )


class RecommendedStop(Dto):
    activity_id: int = Field(serialization_alias="activityId")
    reason: str
    estimated_minutes: int = Field(gt=0, serialization_alias="estimatedMinutes")


class CourseRecommendationResponse(Dto):
    stops: list[RecommendedStop]
    used_ai: bool = Field(serialization_alias="usedAi")
    match_score: int = Field(ge=0, le=100, serialization_alias="matchScore")
