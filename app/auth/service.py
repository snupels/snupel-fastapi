from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.database import get_session
from app.errors import ApiError
from app.security import LoginUser, sign_access_token

from .dto import AuthProvider, AuthResponse, AuthUser
from .oauth import fetch_profile, is_allowed_redirect_uri
from .repository import AuthRepository

password_hasher = PasswordHasher()


class AuthService:
    def __init__(self, repository: AuthRepository) -> None:
        self.repository = repository

    @staticmethod
    def _response(user) -> AuthResponse:
        token, expires_in = sign_access_token(LoginUser(user.id, user.email))
        return AuthResponse(
            access_token=token,
            expires_in=expires_in,
            user=AuthUser(id=user.id, email=user.email),
        )

    async def signup(self, body) -> AuthResponse:
        email = str(body.email).lower()
        if await self.repository.find_user_by_email(email):
            raise ApiError(400, "email_already_exists", "Email is already registered.")
        try:
            user = await self.repository.create_user(
                email=email,
                password_hash=await run_in_threadpool(password_hasher.hash, body.password),
                birth_date=body.birth_date,
                gender=body.gender,
            )
            return self._response(user)
        except IntegrityError as error:
            raise ApiError(400, "email_already_exists", "Email is already registered.") from error

    async def login(self, body) -> AuthResponse:
        user = await self.repository.find_user_by_email(str(body.email).lower())
        if not user or not user.password_hash:
            raise ApiError(400, "invalid_credentials", "Invalid email or password.")
        try:
            await run_in_threadpool(password_hasher.verify, user.password_hash, body.password)
        except (InvalidHashError, VerifyMismatchError):
            raise ApiError(400, "invalid_credentials", "Invalid email or password.") from None
        return self._response(user)

    async def oauth_login(self, provider: AuthProvider, body) -> AuthResponse:
        redirect_uri = str(body.redirect_uri)
        if not is_allowed_redirect_uri(redirect_uri):
            raise ApiError(400, "invalid_request", "redirectUri is not allowed.")
        provider_user_id, profile_email = await run_in_threadpool(
            fetch_profile, provider, body.code, redirect_uri
        )
        user = await self.repository.find_social_user(provider.value, provider_user_id)
        if user:
            return self._response(user)
        email = (profile_email or f"{provider.value}_{provider_user_id}@oauth.snupel.local").lower()
        if await self.repository.find_user_by_email(email):
            raise ApiError(
                400,
                "oauth_email_exists",
                "Email is already registered. Log in before linking OAuth.",
            )
        user = await self.repository.create_user(email=email, password_hash=None)
        await self.repository.create_social_account(
            user_id=user.id,
            provider=provider.value,
            provider_user_id=provider_user_id,
        )
        return self._response(user)


def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService(AuthRepository(session))
