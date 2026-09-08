from pydantic import Field

from app.models import CourseTheme
from app.schemas.common import Dto
from app.schemas.course import CourseResponse


class CourseRecommendationRequest(Dto):
    theme: CourseTheme
    region: str = Field(min_length=1, max_length=100)
    sigun: str | None = Field(default=None, max_length=100)
    sport: str | None = Field(default=None, max_length=100)
    available_minutes: int = Field(
        gt=0, le=1440, validation_alias="availableMinutes", serialization_alias="availableMinutes"
    )


class RecommendedStop(Dto):
    activity_id: int = Field(serialization_alias="activityId")
    place_name: str | None = Field(serialization_alias="placeName")
    address: str | None
    latitude: float | None
    longitude: float | None
    representative_image_url: str | None = Field(serialization_alias="representativeImageUrl")
    reason: str
    estimated_minutes: int = Field(gt=0, serialization_alias="estimatedMinutes")


class RecommendedLeg(Dto):
    from_activity_id: int = Field(serialization_alias="fromActivityId")
    to_activity_id: int = Field(serialization_alias="toActivityId")
    distance_km: float = Field(ge=0, serialization_alias="distanceKm")
    travel_minutes: int = Field(ge=0, serialization_alias="travelMinutes")


class CourseRecommendationResponse(Dto):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    activity_minutes: int = Field(ge=0, serialization_alias="activityMinutes")
    travel_minutes: int = Field(ge=0, serialization_alias="travelMinutes")
    total_estimated_minutes: int = Field(ge=0, serialization_alias="totalEstimatedMinutes")
    stops: list[RecommendedStop]
    legs: list[RecommendedLeg]
    used_ai: bool = Field(serialization_alias="usedAi")
    match_score: int = Field(ge=0, le=100, serialization_alias="matchScore")


class MissionGenerationRequest(CourseRecommendationRequest):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None


class MissionGenerationResponse(CourseRecommendationResponse):
    course: CourseResponse
