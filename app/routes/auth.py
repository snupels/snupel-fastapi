import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.exceptions import ApiError
from app.deps.rate_limit import RateLimiter
from app.schemas.auth import (
    AuthProvider,
    AuthResponse,
    LoginRequest,
    OAuthAuthorizeResponse,
    OAuthLoginRequest,
    SignupRequest,
)
from app.services.auth import AuthService, get_auth_service
from app.services.oauth import authorization_url, is_allowed_redirect_uri

rate_limiter = RateLimiter(20)


def rate_limit(request: Request) -> None:
    host = request.client.host if request.client else "local"
    key = f"{host}:{request.url.path}"
    if not rate_limiter.allow(key):
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
