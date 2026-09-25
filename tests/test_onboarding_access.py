import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.deps.auth import LoginUser, sign_access_token, verify_access_token
from app.main import app
from app.routes.auth import rate_limit
from app.schemas.auth import AuthProvider, OAuthLoginRequest
from app.services.auth import AuthService, get_auth_service


@pytest.mark.parametrize("provider", [AuthProvider.kakao, AuthProvider.google])
def test_new_social_account_requires_own_terms_and_server_blocks_member_actions(monkeypatch, provider):
    monkeypatch.setenv("JWT_SECRET", "onboarding-access-test-secret")
    monkeypatch.setenv("AUTH_ALLOWED_REDIRECT_URIS", "https://sportspassport.kr/login/")
    email = "google-test@example.com" if provider is AuthProvider.google else None
    monkeypatch.setattr("app.services.auth.fetch_profile", lambda *_: ("social-test-21", email))
    class Repository:
        user = None
        async def find_social_user(self, *_): return self.user
        async def find_user_by_email(self, *_): return None
        async def find_user_by_id(self, item_id, **_): return self.user if item_id == 21 else None
        async def create_user(self, **values):
            self.user = SimpleNamespace(id=21, **values)
            return self.user
        async def create_social_account(self, **values):
            assert values["user_id"] == 21 and values["provider"] == provider.value
        async def update_profile(self, user, **values):
            for key, value in values.items():
                setattr(user, key, value)
            return user
    repository = Repository()
    service = AuthService(repository)
    auth = asyncio.run(service.oauth_login(provider, OAuthLoginRequest(
        code="test-only", state="test", redirectUri="https://sportspassport.kr/login/")))
    assert auth.user.onboarding_required is True
    actor = verify_access_token(auth.access_token)
    assert actor.id == 21 and actor.onboarding_required is True
    headers = {"Authorization": f"Bearer {auth.access_token}"}
    app.dependency_overrides[get_auth_service] = lambda: service
    app.dependency_overrides[rate_limit] = lambda: None
    try:
        with TestClient(app) as client:
            assert client.get("/api/auth/me", headers=headers).status_code == 200
            protected = [
                ("GET", "/api/stamp-submissions", None),
                ("POST", "/api/community-feed/1/like", None),
                ("POST", "/api/community-feed/1/comments", {"content": "test"}),
                ("POST", "/api/community-profiles/1/follow", None),
                ("GET", "/api/admin/stamp-submissions", None),
            ]
            for method, url, body in protected:
                response = client.request(method, url, headers=headers, json=body)
                assert response.status_code == 403, response.text
                assert response.json()["error"] == "onboarding_required"
            assert client.post("/api/auth/complete-onboarding").status_code == 401
            assert client.post("/api/auth/complete-onboarding", headers=headers).status_code == 403
            assert client.patch("/api/auth/me", headers=headers, json={"agreeTerms": False}).status_code == 400
            partial = client.patch("/api/auth/me", headers=headers,
                json={"nickname": "카카오회원", "phoneNumber": "01012345678", "agreeTerms": True})
            assert partial.json()["onboardingRequired"] is True
            assert client.post("/api/auth/complete-onboarding", headers=headers).status_code == 403
            completed = client.patch("/api/auth/me", headers=headers, json={
                "agreePrivacy": True, "agreeMarketingEmail": False, "agreeMarketingSns": False})
            assert completed.json()["onboardingRequired"] is False
            result = client.post("/api/auth/complete-onboarding", headers=headers)
            assert result.status_code == 200
            new_actor = verify_access_token(result.json()["accessToken"])
            assert new_actor.id == 21 and new_actor.onboarding_required is False
            assert repository.user.marketing_email_agreed is False
            assert repository.user.marketing_sns_agreed is False
            assert client.get("/api/stamp-submissions", headers=headers).status_code == 403
            before = repository.user.terms_agreed_at
            repeat = asyncio.run(service.oauth_login(provider, OAuthLoginRequest(
                code="test-again", state="test", redirectUri="https://sportspassport.kr/login/")))
            assert repeat.user.id == 21 and not repeat.user.onboarding_required
            assert repository.user.terms_agreed_at == before
    finally:
        app.dependency_overrides.pop(get_auth_service, None)
        app.dependency_overrides.pop(rate_limit, None)


def test_regular_login_also_keeps_incomplete_accounts_restricted(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "onboarding-test-secret")
    service = AuthService(None)
    user = SimpleNamespace(id=3, email="member@example.com", nickname="회원",
                           phone_number="01012345678", terms_agreed_at=datetime.now())
    assert verify_access_token(service._response(user).access_token).onboarding_required
    user.privacy_agreed_at = datetime.now()
    assert not verify_access_token(service._response(user).access_token).onboarding_required
    normal = verify_access_token(sign_access_token(LoginUser(3, user.email))[0])
    assert normal.id == 3 and not normal.onboarding_required
