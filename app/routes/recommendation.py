from fastapi import APIRouter, Depends

from app.deps.auth import LoginUser, require_admin, require_user
from app.deps.rate_limit import RateLimiter
from app.exceptions import ApiError
from app.schemas.recommendation import (
    CourseRecommendationRequest,
    CourseRecommendationResponse,
    MissionGenerationRequest,
    MissionGenerationResponse,
)
from app.services.recommendation import get_recommendation_service

router = APIRouter(prefix="/api/course-recommendations", tags=["Course recommendations"])
admin_router = APIRouter(prefix="/api/admin/course-missions", tags=["Course recommendations"])
rate_limiter = RateLimiter(10)


@router.post("", response_model=CourseRecommendationResponse)
async def recommend(
    body: CourseRecommendationRequest,
    actor: LoginUser = Depends(require_user),
    service=Depends(get_recommendation_service),
):
    if not rate_limiter.allow(str(actor.id)):
        raise ApiError(429, "rate_limited", "Too many requests.")
    return await service.recommend(body)


@admin_router.post(
    "/generate",
    response_model=MissionGenerationResponse,
    status_code=201,
    tags=["Course recommendations"],
)
async def generate_mission(
    body: MissionGenerationRequest,
    actor: LoginUser = Depends(require_admin),
    service=Depends(get_recommendation_service),
):
    if not rate_limiter.allow(str(actor.id)):
        raise ApiError(429, "rate_limited", "Too many requests.")
    return await service.generate_mission(body)
