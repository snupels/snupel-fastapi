from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .admin import setup_admin
from .activities.router import router as activities_router
from .auth.router import router as auth_router
from .badges.router import router as badges_router
from .collected_badges.router import router as collected_badges_router
from .collected_stamps.router import router as collected_stamps_router
from .courses.router import router as courses_router
from .errors import ApiError, api_error_handler
from .passports.router import router as passports_router

app = FastAPI(
    title="Snupel API",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/api/docs",
)
app.add_exception_handler(ApiError, api_error_handler)
setup_admin(app)


@app.exception_handler(RequestValidationError)
def validation_error(request: Request, _: RequestValidationError) -> JSONResponse:
    auth = request.url.path.startswith("/api/auth/")
    return JSONResponse(
        status_code=400,
        content={
            "error": "invalid_request" if auth else "bad_request",
            "message": "Invalid request body.",
        },
    )


@app.get("/api/health", tags=["System"])
def health() -> dict[str, str]:
    return {"status": "ok"}


for router in (
    auth_router,
    badges_router,
    activities_router,
    courses_router,
    passports_router,
    collected_badges_router,
    collected_stamps_router,
):
    app.include_router(router)
