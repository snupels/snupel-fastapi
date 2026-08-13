from fastapi import Depends, Path

from app.routes.base import create_crud_router

from app.schemas.course import (
    CourseCreate,
    CourseItineraryResponse,
    CoursePatch,
    CourseResponse,
)
from app.services.course import get_course_service

router = create_crud_router(
    prefix="/api/courses",
    tag="Courses",
    create_model=CourseCreate,
    patch_model=CoursePatch,
    response_model=CourseResponse,
    service_dependency=get_course_service,
)


@router.get("/{item_id}/itinerary", response_model=CourseItineraryResponse)
async def course_itinerary(
    item_id: int = Path(gt=0),
    service=Depends(get_course_service),
):
    return await service.itinerary(item_id)
