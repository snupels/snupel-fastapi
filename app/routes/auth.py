import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.exceptions import ApiError
from app.deps.auth import LoginUser, require_user
from app.deps.rate_limit import RateLimiter
from app.schemas.auth import (
    AccountReminderRequest,
    AuthProvider,
    AuthResponse,
    LoginRequest,
    MessageResponse,
    OAuthAuthorizeResponse,
    OAuthLoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    ProfileUpdateRequest,
    ProfileUploadRequest,
    ProfileUploadResponse,
    SignupRequest,
    AuthUser,
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


def set_oauth_state_cookie(response: Response, provider: str, state: str) -> None:
    response.set_cookie(
        f"oauth_state_{provider}",
        state,
        max_age=600,
        path=f"/api/auth/oauth/{provider}/login",
        httponly=True,
        samesite="lax",
        secure=os.getenv("ENVIRONMENT") == "production",
    )


@router.post("/signup", response_model=AuthResponse, status_code=201)
async def signup(body: SignupRequest, service: AuthService = Depends(get_auth_service)):
    return await service.signup(body)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, service: AuthService = Depends(get_auth_service)):
    return await service.login(body)


@router.get("/me", response_model=AuthUser)
async def me(
    actor: LoginUser = Depends(require_user),
    service: AuthService = Depends(get_auth_service),
):
    return await service.me(actor)


@router.patch("/me", response_model=AuthUser)
async def update_me(
    body: ProfileUpdateRequest,
    actor: LoginUser = Depends(require_user),
    service: AuthService = Depends(get_auth_service),
):
    return await service.update_profile(actor, body)


@router.post("/profile-photo/upload-url", response_model=ProfileUploadResponse)
async def profile_photo_upload_url(
    body: ProfileUploadRequest,
    actor: LoginUser = Depends(require_user),
    service: AuthService = Depends(get_auth_service),
):
    return await service.profile_upload(actor, body.content_type)


@router.post("/account-reminder", response_model=MessageResponse)
async def account_reminder(
    body: AccountReminderRequest,
    service: AuthService = Depends(get_auth_service),
):
    await service.account_reminder(str(body.email))
    return {"message": "If the account exists, an email has been sent."}


@router.post("/password-reset/request", response_model=MessageResponse)
async def request_password_reset(
    body: PasswordResetRequest,
    service: AuthService = Depends(get_auth_service),
):
    await service.request_password_reset(str(body.email))
    return {"message": "If the account exists, a reset code has been sent."}


@router.post("/password-reset/confirm", response_model=MessageResponse)
async def confirm_password_reset(
    body: PasswordResetConfirm,
    service: AuthService = Depends(get_auth_service),
):
    await service.confirm_password_reset(body)
    return {"message": "Password has been reset."}


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
    set_oauth_state_cookie(response, provider, state)
    return OAuthAuthorizeResponse(
        provider=parsed_provider,
        authorization_url=authorization_url(parsed_provider, redirect_uri, state),
    )


@router.get("/oauth/{provider}/start", response_class=RedirectResponse, status_code=302)
def start_oauth(
    provider: str,
    redirect_uri: Annotated[str, Query(alias="redirectUri")],
):
    parsed_provider = provider_from(provider)
    if not is_allowed_redirect_uri(redirect_uri):
        raise ApiError(400, "invalid_request", "redirectUri is not allowed.")
    state = secrets.token_urlsafe(32)
    response = RedirectResponse(
        authorization_url(parsed_provider, redirect_uri, state),
        status_code=302,
    )
    set_oauth_state_cookie(response, provider, state)
    return response


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
