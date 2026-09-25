import base64
import binascii
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import admins, mission_reviewers, production_secret
from app.exceptions import ApiError

DEFAULT_EXPIRES_IN = 60 * 60 * 24 * 7
bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class LoginUser:
    id: int
    email: str
    onboarding_required: bool = False


def _secret() -> bytes:
    value = os.getenv("JWT_SECRET")
    if not value:
        raise RuntimeError("JWT_SECRET is required.")
    production_secret("JWT_SECRET", value)
    return value.encode()


def access_token_expires_in() -> int:
    try:
        value = int(os.getenv("AUTH_ACCESS_TOKEN_EXPIRES_IN", ""))
        return value if value > 0 else DEFAULT_EXPIRES_IN
    except ValueError:
        return DEFAULT_EXPIRES_IN


def _encode(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _decode(value: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))


def sign_access_token(user: LoginUser, now: int | None = None) -> tuple[str, int]:
    issued_at = int(time.time()) if now is None else now
    expires_in = access_token_expires_in()
    header = _encode({"alg": "HS256", "typ": "JWT"})
    payload = _encode(
        {"sub": str(user.id), "email": user.email, "iat": issued_at, "exp": issued_at + expires_in,
         "onboarding_required": user.onboarding_required}
    )
    signing_input = f"{header}.{payload}"
    signature = base64.urlsafe_b64encode(
        hmac.new(_secret(), signing_input.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return f"{signing_input}.{signature}", expires_in


def verify_access_token(token: str, now: int | None = None) -> LoginUser | None:
    try:
        header, payload, signature = token.split(".")
        expected = base64.urlsafe_b64encode(
            hmac.new(_secret(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        ).rstrip(b"=").decode()
        head, body = _decode(header), _decode(payload)
        user_id = int(body["sub"])
        current = int(time.time()) if now is None else now
        if (
            not hmac.compare_digest(signature, expected)
            or head != {"alg": "HS256", "typ": "JWT"}
            or user_id <= 0
            or not isinstance(body.get("email"), str)
            or not isinstance(body.get("exp"), int)
            or body["exp"] <= current
            or not isinstance(body.get("onboarding_required", False), bool)
        ):
            return None
        return LoginUser(user_id, body["email"], body.get("onboarding_required", False))
    except (
        ValueError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        binascii.Error,
        json.JSONDecodeError,
    ):
        return None


def authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> LoginUser | None:
    return verify_access_token(credentials.credentials) if credentials else None


def optional_user(user: LoginUser | None = Depends(authenticated_user)) -> LoginUser | None:
    return user if user and not user.onboarding_required else None


def require_authenticated_user(user: LoginUser | None = Depends(authenticated_user)) -> LoginUser:
    if not user:
        raise ApiError(401, "unauthorized", "Login is required.")
    return user


def require_user(user: LoginUser = Depends(require_authenticated_user)) -> LoginUser:
    if user.onboarding_required:
        raise ApiError(403, "onboarding_required", "Complete profile and required consents first.")
    return user


def require_admin(user: LoginUser = Depends(require_user)) -> LoginUser:
    if not is_admin(user):
        raise ApiError(403, "forbidden", "Administrator access is required.")
    return user


def is_admin(user: LoginUser) -> bool:
    return user.email.lower() in admins()


def require_mission_reviewer(user: LoginUser = Depends(require_user)) -> LoginUser:
    if user.email.lower() not in mission_reviewers():
        raise ApiError(403, "forbidden", "Mission reviewer access is required.")
    return user
