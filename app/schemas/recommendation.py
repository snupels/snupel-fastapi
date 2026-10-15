from datetime import date
from typing import Literal

from pydantic import Field, field_serializer

from app.models import CourseTheme
from app.schemas.common import Dto
from app.schemas.course import CourseResponse
from app.place_quality import display_address


class CourseRecommendationRequest(Dto):
    theme: CourseTheme
    region: str = Field(min_length=1, max_length=100)
    sigun: str | None = Field(default=None, max_length=100)
    sport: str | None = Field(default=None, max_length=100)
    travel_date: date | None = Field(default=None, validation_alias="travelDate", serialization_alias="travelDate")
    start_time: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
                            validation_alias="startTime", serialization_alias="startTime")
    available_minutes: int = Field(
        gt=0, le=1440, validation_alias="availableMinutes", serialization_alias="availableMinutes"
    )


class RecommendedStop(Dto):
    @field_serializer("address", check_fields=False)
    def serialize_address(self, value):
        return display_address(value)

    activity_id: int = Field(serialization_alias="activityId")
    place_name: str | None = Field(serialization_alias="placeName")
    address: str | None
    latitude: float | None
    longitude: float | None
    representative_image_url: str | None = Field(serialization_alias="representativeImageUrl")
    reason: str
    estimated_minutes: int = Field(gt=0, serialization_alias="estimatedMinutes")
    role: Literal["activity", "meal", "sightseeing", "rest"] | None = None
    arrival_time: str | None = Field(default=None, serialization_alias="arrivalTime")
    departure_time: str | None = Field(default=None, serialization_alias="departureTime")
    waiting_minutes: int | None = Field(default=None, ge=0, serialization_alias="waitingMinutes")
    hours_status: Literal["provided", "unknown"] | None = Field(default=None, serialization_alias="hoursStatus")
    opening_hours: str | None = Field(default=None, serialization_alias="openingHours")
    visit_note: str | None = Field(default=None, serialization_alias="visitNote")


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
    travel_date: date | None = Field(default=None, serialization_alias="travelDate")
    start_time: str | None = Field(default=None, serialization_alias="startTime")
    waiting_minutes: int | None = Field(default=None, ge=0, serialization_alias="waitingMinutes")
    planning_notes: list[str] | None = Field(default=None, serialization_alias="planningNotes")


class MissionGenerationRequest(CourseRecommendationRequest):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None


class MissionGenerationResponse(CourseRecommendationResponse):
    course: CourseResponse
