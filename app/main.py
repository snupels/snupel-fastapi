import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .admin import setup_admin
from .exceptions import ApiError, api_error_handler
from .routes.activity import router as activities_router
from .routes.auth import router as auth_router
from .routes.badge import router as badges_router
from .routes.collected_badge import router as collected_badges_router
from .routes.collected_stamp import router as collected_stamps_router
from .routes.course import router as courses_router
from .routes.me import admin_router as reward_claims_router
from .routes.me import router as me_router
from .routes.passport import router as passports_router
from .routes.recommendation import admin_router as admin_missions_router
from .routes.recommendation import router as recommendations_router
from .routes.stamp_submission import router as stamp_submissions_router
from .routes.stamp_catalog import router as stamp_catalog_router
from .routes.stampbook import router as stampbook_router
from .routes.weather import router as weather_router

app = FastAPI(
    title="Snupel API",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/api/docs",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://sportspassport.kr"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(ApiError, api_error_handler)
setup_admin(app)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith(
        (
            "/api/auth",
            "/api/me",
            "/api/passports",
            "/api/collected-stamps",
            "/api/collected-badges",
            "/api/stamp-submissions",
            "/api/community-feed",
            "/api/admin",
            "/admin",
        )
    ):
        response.headers["Cache-Control"] = "no-store"
    if os.getenv("ENVIRONMENT") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


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
    stamp_submissions_router,
    stamp_catalog_router,
    stampbook_router,
    me_router,
    reward_claims_router,
    recommendations_router,
    admin_missions_router,
    weather_router,
):
    app.include_router(router)
