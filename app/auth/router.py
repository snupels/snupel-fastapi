import os
import secrets
import time
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.errors import ApiError

from .dto import (
    AuthProvider,
    AuthResponse,
    LoginRequest,
    OAuthAuthorizeResponse,
    OAuthLoginRequest,
    SignupRequest,
)
from .oauth import authorization_url, is_allowed_redirect_uri
from .service import AuthService, get_auth_service

rate_limits: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0))


def rate_limit(request: Request) -> None:
    now = time.monotonic()
    host = request.client.host if request.client else "local"
    key = f"{host}:{request.url.path}"
    count, reset_at = rate_limits[key]
    if reset_at <= now:
        rate_limits[key] = (1, now + 60)
        return
    count += 1
    rate_limits[key] = (count, reset_at)
    # ponytail: process-local limiter; move to Redis when running multiple API instances.
    if count > 20:
        raise ApiError(429, "rate_limited", "Too many requests.")


router = APIRouter(prefix="/api/auth", tags=["Auth"], dependencies=[Depends(rate_limit)])


def provider_from(value: str) -> AuthProvider:
    try:
        return AuthProvider(value)
    except ValueError:
        raise ApiError(400, "unsupported_provider", "Unsupported OAuth provider.") from None


@router.post("/signup", response_model=AuthResponse, status_code=201)
async def signup(body: SignupRequest, service: AuthService = Depends(get_auth_service)):
    return await service.signup(body)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, service: AuthService = Depends(get_auth_service)):
    return await service.login(body)


@router.get("/oauth/{provider}/authorize", response_model=OAuthAuthorizeResponse)
def authorize(
    provider: str,
    response: Response,
    redirect_uri: Annotated[str, Query(alias="redirectUri")],
):
    parsed_provider = provider_from(provider)
    if not is_allowed_redirect_uri(redirect_uri):
        raise ApiError(400, "invalid_request", "redirectUri is not allowed.")
    state = secrets.token_urlsafe(32)
    response.set_cookie(
        f"oauth_state_{provider}",
        state,
        max_age=600,
        path=f"/api/auth/oauth/{provider}/login",
        httponly=True,
        samesite="lax",
        secure=os.getenv("ENVIRONMENT") == "production",
    )
    return OAuthAuthorizeResponse(
        provider=parsed_provider,
        authorization_url=authorization_url(parsed_provider, redirect_uri, state),
    )


@router.post("/oauth/{provider}/login", response_model=AuthResponse)
async def oauth_login(
    provider: str,
    body: OAuthLoginRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    parsed_provider = provider_from(provider)
    expected_state = request.cookies.get(f"oauth_state_{provider}")
    if not expected_state or body.state != expected_state:
        raise ApiError(400, "invalid_oauth_state", "Invalid OAuth state.")
    result = await service.oauth_login(parsed_provider, body)
    response.delete_cookie(f"oauth_state_{provider}", path=f"/api/auth/oauth/{provider}/login")
    return result
