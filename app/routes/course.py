from app.routes.base import create_crud_router

from app.schemas.course import CourseCreate, CoursePatch, CourseResponse
from app.services.course import get_course_service

router = create_crud_router(
    prefix="/api/courses",
    tag="Courses",
    create_model=CourseCreate,
    patch_model=CoursePatch,
    response_model=CourseResponse,
    service_dependency=get_course_service,
)
