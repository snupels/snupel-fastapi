from app.router import create_crud_router

from .dto import CourseCreate, CoursePatch, CourseResponse
from .service import get_course_service

router = create_crud_router(
    prefix="/api/courses",
    tag="Courses",
    create_model=CourseCreate,
    patch_model=CoursePatch,
    response_model=CourseResponse,
    service_dependency=get_course_service,
)

