import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.deps.auth import LoginUser, sign_access_token
from app.exceptions import ApiError
from app.main import app
from app.schemas.auth import PasswordResetConfirm, ProfileUpdateRequest, SignupRequest
from app.services.auth import AuthService, get_auth_service


def _token() -> str:
    return sign_access_token(LoginUser(7, "user@example.com"))[0]


def test_profile_routes_require_login_and_validate_updates(monkeypatch):
    class Service:
        async def me(self, actor):
            assert actor.id == 7
            return {
                "id": 7,
                "email": "user@example.com",
                "nickname": "강원러너",
                "profile_image_url": None,
                "birth_date": None,
                "gender": None,
            }

        async def update_profile(self, actor, body):
            assert actor.id == 7
            assert body.nickname == "새닉네임"
            return await self.me(actor) | {"nickname": body.nickname}

    monkeypatch.setenv("JWT_SECRET", "account-test-secret")
    app.dependency_overrides[get_auth_service] = Service
    try:
        with TestClient(app) as client:
            assert client.get("/api/auth/me").status_code == 401
            headers = {"Authorization": f"Bearer {_token()}"}
            assert client.get("/api/auth/me", headers=headers).json()["nickname"] == "강원러너"
            updated = client.patch("/api/auth/me", json={"nickname": "새닉네임"}, headers=headers)
            invalid = client.patch("/api/auth/me", json={"nickname": "한"}, headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert updated.status_code == 200
    assert updated.json()["nickname"] == "새닉네임"
    assert invalid.status_code == 400


def test_profile_update_only_changes_supplied_fields():
    user = SimpleNamespace(
        id=7,
        email="user@example.com",
        nickname="기존닉네임",
        profile_image_key="profiles/7/existing.jpg",
        birth_date=None,
        gender=None,
    )

    class Repository:
        async def find_user_by_id(self, _user_id):
            return user

        async def update_profile(self, row, **values):
            assert values == {"nickname": "새닉네임"}
            for key, value in values.items():
                setattr(row, key, value)
            return row

    result = asyncio.run(
        AuthService(Repository()).update_profile(
            LoginUser(7, "user@example.com"),
            ProfileUpdateRequest(nickname="새닉네임"),
        )
    )
    assert result.nickname == "새닉네임"
    assert user.profile_image_key == "profiles/7/existing.jpg"


def test_password_reset_rejects_expired_or_wrong_code(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "account-test-secret")
    user = SimpleNamespace(id=7, email="user@example.com")
    reset = SimpleNamespace(
        code_hash=AuthService._code_hash(user.email, "123456"),
        expires_at=datetime.now() + timedelta(minutes=5),
    )

    class Repository:
        async def find_user_by_email(self, _email):
            return user

        async def active_reset_code(self, _user_id):
            return reset

        async def reset_password(self, *_args):
            raise AssertionError("password must not be changed")

    with pytest.raises(ApiError) as error:
        asyncio.run(
            AuthService(Repository()).confirm_password_reset(
                PasswordResetConfirm(
                    email=user.email,
                    code="654321",
                    newPassword="new-password",
                )
            )
        )
    assert (error.value.status, error.value.code) == (400, "invalid_reset_code")


def test_signup_requires_terms_privacy_and_nickname():
    with pytest.raises(ValidationError):
        SignupRequest(email="user@example.com", password="password123")

    request = SignupRequest(
        email="user@example.com",
        password="password123",
        nickname="강원러너",
        phoneNumber="010-1234-5678",
        agreeTerms=True,
        agreePrivacy=True,
    )
    assert request.nickname == "강원러너"
    assert request.phone_number == "01012345678"
    assert request.agree_terms is True
    assert request.agree_privacy is True


def test_onboarding_requires_profile_nickname_and_required_consents():
    complete = SimpleNamespace(
        id=7,
        email="user@example.com",
        nickname="강원러너",
        phone_number="01012345678",
        profile_image_key="profiles/7/photo.jpg",
        birth_date=None,
        gender=None,
        terms_agreed_at=datetime.now(),
        privacy_agreed_at=datetime.now(),
        marketing_email_agreed=False,
        marketing_sns_agreed=False,
    )
    assert AuthService(object())._user(complete).onboarding_required is False
    complete.profile_image_key = None
    assert AuthService(object())._user(complete).onboarding_required is True
