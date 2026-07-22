from fastapi import APIRouter, Depends

from app.deps.auth import LoginUser, require_user
from app.schemas.recommendation import CourseRecommendationRequest, CourseRecommendationResponse
from app.services.recommendation import get_recommendation_service

router = APIRouter(prefix="/api/course-recommendations", tags=["Course recommendations"])


@router.post("", response_model=CourseRecommendationResponse)
async def recommend(
    body: CourseRecommendationRequest,
    _: LoginUser = Depends(require_user),
    service=Depends(get_recommendation_service),
):
    return await service.recommend(body)
