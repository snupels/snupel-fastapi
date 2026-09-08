from datetime import datetime, timedelta
from hashlib import sha256
import hmac
import logging
import os
import secrets
import smtplib

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config.database import get_session
from app.deps.auth import LoginUser, sign_access_token
from app.exceptions import ApiError
from app.repositories.auth import AuthRepository
from app.schemas.auth import AuthProvider, AuthResponse, AuthUser
from app.services.mail import send_mail
from app.services.storage import ProofStorage, get_proof_storage
from .oauth import fetch_profile, is_allowed_redirect_uri

password_hasher = PasswordHasher()
logger = logging.getLogger(__name__)


def _duplicate_identity(error: IntegrityError) -> ApiError | None:
    # Inspect constraint names only; never return database details or values.
    detail = str(error.orig).lower()
    if "users_username_unique" in detail or "users.username" in detail:
        return ApiError(400, "username_already_exists", "Username is already registered.")
    if "users_email_unique" in detail or "users.email" in detail:
        return ApiError(400, "email_already_exists", "Email is already registered.")
    return None


class AuthService:
    def __init__(self, repository: AuthRepository, storage: ProofStorage | None = None) -> None:
        self.repository = repository
        self.storage = storage

    def _user(self, user) -> AuthUser:
        profile_url = (
            self.storage.proof_url(getattr(user, "profile_image_key", None))
            if self.storage and getattr(user, "profile_image_key", None)
            else None
        )
        return AuthUser(
            id=user.id,
            email=user.email,
            username=getattr(user, "username", None),
            nickname=getattr(user, "nickname", None),
            phone_number=getattr(user, "phone_number", None),
            postal_code=getattr(user, "postal_code", None),
            address=getattr(user, "address", None),
            address_detail=getattr(user, "address_detail", None),
            profile_image_url=profile_url,
            birth_date=getattr(user, "birth_date", None),
            gender=getattr(user, "gender", None),
            onboarding_required=not all(
                (
                    getattr(user, "nickname", None),
                    getattr(user, "phone_number", None),
                    getattr(user, "terms_agreed_at", None),
                    getattr(user, "privacy_agreed_at", None),
                )
            ),
            marketing_email_agreed=getattr(user, "marketing_email_agreed", False),
            marketing_sns_agreed=getattr(user, "marketing_sns_agreed", False),
        )

    def _response(self, user) -> AuthResponse:
        token, expires_in = sign_access_token(LoginUser(user.id, user.email))
        return AuthResponse(
            access_token=token,
            expires_in=expires_in,
            user=self._user(user),
        )

    async def signup(self, body) -> AuthResponse:
        email = str(body.email).lower()
        if await self.repository.find_user_by_email(email):
            raise ApiError(400, "email_already_exists", "Email is already registered.")
        if await self.repository.find_user_by_username(body.username):
            raise ApiError(400, "username_already_exists", "Username is already registered.")
        try:
            agreed_at = datetime.now()
            user = await self.repository.create_user(
                email=email,
                username=body.username,
                password_hash=await run_in_threadpool(password_hasher.hash, body.password),
                birth_date=body.birth_date,
                gender=body.gender,
                nickname=body.nickname.strip(),
                phone_number=body.phone_number,
                postal_code=body.postal_code,
                address=body.address,
                address_detail=body.address_detail,
                terms_agreed_at=agreed_at,
                privacy_agreed_at=agreed_at,
                marketing_email_agreed=body.agree_marketing_email,
                marketing_sns_agreed=body.agree_marketing_sns,
            )
            return self._response(user)
        except IntegrityError as error:
            duplicate = _duplicate_identity(error)
            if duplicate:
                raise duplicate from None
            raise

    async def username_availability(self, username: str):
        return {"username": username, "available": await self.repository.find_user_by_username(username) is None}

    async def login(self, body) -> AuthResponse:
        identifier = body.identifier
        user = (
            await self.repository.find_user_by_email(identifier)
            if "@" in identifier else await self.repository.find_user_by_username(identifier)
        )
        if not user or not user.password_hash:
            raise ApiError(400, "invalid_credentials", "Invalid username, email or password.")
        try:
            await run_in_threadpool(password_hasher.verify, user.password_hash, body.password)
        except (InvalidHashError, VerifyMismatchError):
            raise ApiError(400, "invalid_credentials", "Invalid username, email or password.") from None
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
        email = (
            profile_email or f"{provider.value}_{provider_user_id}@oauth.sportspassport.kr"
        ).lower()
        user = await self.repository.find_user_by_email(email)
        if not user:
            user = await self.repository.create_user(email=email, password_hash=None)
        await self.repository.create_social_account(
            user_id=user.id,
            provider=provider.value,
            provider_user_id=provider_user_id,
        )
        return self._response(user)

    async def verify_password(self, actor: LoginUser, current_password: str) -> None:
        user = await self.repository.find_user_by_id(actor.id)
        if not user or not user.password_hash:
            raise ApiError(400, "password_unavailable", "Password verification is unavailable for this account.")
        try:
            await run_in_threadpool(password_hasher.verify, user.password_hash, current_password)
        except (InvalidHashError, VerifyMismatchError):
            raise ApiError(400, "invalid_credentials", "Current password is incorrect.") from None

    async def change_password(self, actor: LoginUser, current_password: str, new_password: str) -> None:
        user = await self.repository.find_user_by_id(actor.id)
        if not user or not user.password_hash:
            raise ApiError(400, "password_unavailable", "Password change is unavailable for this account.")
        try:
            await run_in_threadpool(password_hasher.verify, user.password_hash, current_password)
        except (InvalidHashError, VerifyMismatchError):
            raise ApiError(400, "invalid_credentials", "Current password is incorrect.") from None
        await self.repository.change_password(
            user,
            await run_in_threadpool(password_hasher.hash, new_password),
        )

    async def me(self, actor: LoginUser) -> AuthUser:
        user = await self.repository.find_user_by_id(actor.id)
        if not user:
            raise ApiError(404, "not_found", "User not found.")
        return self._user(user)

    async def update_profile(self, actor: LoginUser, body) -> AuthUser:
        assigning_username = "username" in body.model_fields_set
        user = (
            await self.repository.find_user_by_id(actor.id, lock=True)
            if assigning_username else await self.repository.find_user_by_id(actor.id)
        )
        if not user:
            raise ApiError(404, "not_found", "User not found.")
        username_values = {}
        if assigning_username:
            current_username = getattr(user, "username", None)
            if body.username is None or (current_username is not None and current_username != body.username):
                raise ApiError(400, "username_change_not_allowed", "Username can only be set once and cannot be cleared.")
            if current_username is None:
                if await self.repository.find_user_by_username(body.username):
                    raise ApiError(400, "username_already_exists", "Username is already registered.")
                username_values["username"] = body.username
        if body.profile_image_key:
            prefix = f"profiles/{actor.id}/"
            if not body.profile_image_key.startswith(prefix):
                raise ApiError(400, "bad_request", "Invalid profile image object key.")
            if not self.storage:
                raise ApiError(503, "storage_unavailable", "Profile image storage is unavailable.")
            await run_in_threadpool(self.storage.validate, body.profile_image_key)
        values = username_values | {
            field: getattr(body, field)
            for field in (
                "nickname", "phone_number", "profile_image_key", "birth_date", "gender",
                "postal_code", "address", "address_detail",
            )
            if field in body.model_fields_set
        }
        now = datetime.now()
        if body.agree_terms is True and not getattr(user, "terms_agreed_at", None):
            values["terms_agreed_at"] = now
        if body.agree_privacy is True and not getattr(user, "privacy_agreed_at", None):
            values["privacy_agreed_at"] = now
        if body.agree_marketing_email is not None:
            values["marketing_email_agreed"] = body.agree_marketing_email
        if body.agree_marketing_sns is not None:
            values["marketing_sns_agreed"] = body.agree_marketing_sns
        try:
            updated = await self.repository.update_profile(user, **values)
        except IntegrityError as error:
            duplicate = _duplicate_identity(error)
            if duplicate:
                raise duplicate from None
            raise
        return self._user(updated)

    async def profile_upload(self, actor: LoginUser, content_type: str):
        if not self.storage:
            raise ApiError(503, "storage_unavailable", "Profile image storage is unavailable.")
        return self.storage.profile_upload(actor.id, content_type)

    @staticmethod
    def _code_hash(email: str, code: str) -> str:
        secret = os.getenv("JWT_SECRET", "development-reset-secret")
        return sha256(f"{secret}:{email}:{code}".encode()).hexdigest()

    async def account_reminder(self, email: str) -> None:
        normalized = email.strip().lower()
        user = await self.repository.find_user_by_email(normalized)
        if user:
            identifier = getattr(user, "username", None) or normalized
            await self._send_recovery_mail(
                normalized,
                "[강원 스포츠 패스포트] 아이디 안내",
                f"회원님의 로그인 아이디는 {identifier} 입니다.\n"
                + ("카카오 또는 구글로 가입한 계정은 해당 소셜 로그인을 이용해 주세요.\n" if not getattr(user, "password_hash", None) else "")
                + "본인이 요청하지 않았다면 이 메일을 무시해 주세요.",
            )

    @staticmethod
    async def _send_recovery_mail(email: str, subject: str, content: str) -> bool:
        try:
            await run_in_threadpool(send_mail, email, subject, content)
            return True
        except (KeyError, ValueError, OSError, smtplib.SMTPException):
            # Recovery remains non-enumerating even during mail outages.
            logger.warning("Account recovery email delivery failed.")
            return False

    @staticmethod
    def _matches_reset_identity(user, identifier: str) -> bool:
        if user is None:
            return False
        expected = getattr(user, "username", None) or user.email.lower()
        return hmac.compare_digest(expected.encode("utf-8"), identifier.strip().lower().encode("utf-8"))

    async def request_password_reset(self, email: str, username: str) -> None:
        normalized = email.strip().lower()
        user = await self.repository.find_user_by_email(normalized)
        if not self._matches_reset_identity(user, username):
            return
        if not user.password_hash:
            await self._send_recovery_mail(
                normalized, "[강원 스포츠 패스포트] 로그인 안내",
                "카카오 또는 구글로 가입한 계정은 별도 비밀번호가 없습니다. 가입할 때 사용한 소셜 로그인을 이용해 주세요.",
            )
            return
        code = f"{secrets.randbelow(1_000_000):06d}"
        async with self.repository.reset_code_transaction() as transaction:
            await self.repository.create_reset_code(
                user_id=user.id,
                code_hash=self._code_hash(normalized, code),
                expires_at=datetime.now() + timedelta(minutes=10),
            )
            sent = await self._send_recovery_mail(
                normalized,
                "[강원 스포츠 패스포트] 비밀번호 재설정 인증번호",
                f"비밀번호 재설정 인증번호는 {code} 입니다.\n인증번호는 10분 동안 유효합니다.",
            )
            if not sent:
                # Keep an already-delivered code usable if a resend fails.
                await transaction.rollback()

    async def confirm_password_reset(self, body) -> None:
        normalized = str(body.email).lower()
        user = await self.repository.find_user_by_email(normalized)
        if not self._matches_reset_identity(user, body.username) or not user.password_hash:
            raise ApiError(400, "invalid_reset_code", "Invalid or expired reset code.")
        reset = await self.repository.active_reset_code(user.id)
        supplied_hash = self._code_hash(normalized, body.code)
        if (
            not reset
            or reset.expires_at < datetime.now()
            or not hmac.compare_digest(reset.code_hash, supplied_hash)
        ):
            raise ApiError(400, "invalid_reset_code", "Invalid or expired reset code.")
        await self.repository.reset_password(
            user,
            reset,
            await run_in_threadpool(password_hasher.hash, body.new_password),
        )


def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService(AuthRepository(session), get_proof_storage())
