import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

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


def test_logged_in_user_can_verify_and_change_password(monkeypatch):
    user = SimpleNamespace(id=7, email="user@example.com", password_hash="old-hash")
    changed = {}

    class Repository:
        async def find_user_by_id(self, _user_id):
            return user

        async def change_password(self, row, password_hash):
            changed["user"] = row
            changed["hash"] = password_hash

    monkeypatch.setattr(
        "app.services.auth.password_hasher",
        SimpleNamespace(
            verify=lambda password_hash, password: password_hash == "old-hash" and password == "old-password",
            hash=lambda password: f"hashed:{password}",
        ),
    )
    service = AuthService(Repository())
    actor = LoginUser(7, "user@example.com")

    asyncio.run(service.verify_password(actor, "old-password"))
    asyncio.run(service.change_password(actor, "old-password", "new-password"))

    assert changed == {"user": user, "hash": "hashed:new-password"}


def test_password_verification_rejects_wrong_password(monkeypatch):
    user = SimpleNamespace(id=7, email="user@example.com", password_hash="old-hash")

    class Repository:
        async def find_user_by_id(self, _user_id):
            return user

    def reject_password(*_args):
        from argon2.exceptions import VerifyMismatchError

        raise VerifyMismatchError

    monkeypatch.setattr(
        "app.services.auth.password_hasher",
        SimpleNamespace(verify=reject_password),
    )

    with pytest.raises(ApiError) as error:
        asyncio.run(
            AuthService(Repository()).verify_password(
                LoginUser(7, "user@example.com"), "wrong-password"
            )
        )

    assert (error.value.status, error.value.code) == (400, "invalid_credentials")


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


def test_onboarding_requires_nickname_phone_and_required_consents_but_not_photo():
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
    assert AuthService(object())._user(complete).onboarding_required is False


def test_kakao_oauth_start_redirects_and_rejects_unapproved_redirect(monkeypatch):
    redirect_uri = "https://sportspassport.kr/login/"
    monkeypatch.setenv("KAKAO_CLIENT_ID", "kakao-client")
    monkeypatch.setenv("KAKAO_CLIENT_SECRET", "kakao-secret")
    monkeypatch.setenv("AUTH_ALLOWED_REDIRECT_URIS", redirect_uri)

    with TestClient(app) as client:
        response = client.get(
            "/api/auth/oauth/kakao/start",
            params={"redirectUri": redirect_uri},
            follow_redirects=False,
        )
        invalid = client.get(
            "/api/auth/oauth/kakao/start",
            params={"redirectUri": "https://malicious.example/login/"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    query = parse_qs(location.query)
    assert location.netloc == "kauth.kakao.com"
    assert query["client_id"] == ["kakao-client"]
    assert query["redirect_uri"] == [redirect_uri]
    assert query["state"][0]
    assert "oauth_state_kakao=" in response.headers["set-cookie"]
    assert invalid.status_code == 400
