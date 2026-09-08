import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from app.exceptions import ApiError
from app.main import app
from app.schemas.auth import AuthProvider
from app.services import oauth
from app.services.auth import get_auth_service


@pytest.fixture
def kakao(monkeypatch):
    monkeypatch.setenv("KAKAO_CLIENT_ID", " test-client ")
    monkeypatch.delenv("KAKAO_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("AUTH_ALLOWED_REDIRECT_URIS", "https://sportspassport.kr/login/")


def response(status, body):
    return httpx.Response(status, json=body, request=httpx.Request("POST", "https://provider.example/token"))


def test_kakao_optional_secret_and_missing_email(kakao, monkeypatch):
    captured = {}

    def post(url, *, data, timeout):
        captured.update(data)
        return response(200, {"access_token": "test-token"})

    monkeypatch.setattr(oauth.httpx, "post", post)
    monkeypatch.setattr(oauth.httpx, "get", lambda *a, **k: response(200, {"id": 7, "kakao_account": None}))
    assert oauth.fetch_profile(AuthProvider.kakao, "code", "https://sportspassport.kr/login/") == ("7", None)
    assert captured["client_id"] == "test-client"
    assert "client_secret" not in captured


@pytest.mark.parametrize("payload,status,code", [
    ({"error": "invalid_grant", "error_code": "KOE320"}, 400, "oauth_code_expired"),
    ({"error": "invalid_client", "error_code": "KOE010"}, 503, "oauth_not_configured"),
    ({"error": "invalid_request", "error_code": "KOE322"}, 503, "oauth_not_configured"),
    ({"error": "server_error"}, 502, "oauth_unavailable"),
])
def test_provider_errors_are_actionable_without_leaking_payload(kakao, monkeypatch, payload, status, code):
    payload["error_description"] = "sensitive-code-and-secret"
    monkeypatch.setattr(oauth.httpx, "post", lambda *a, **k: response(400, payload))
    with pytest.raises(ApiError) as failure:
        oauth.fetch_profile(AuthProvider.kakao, "code", "https://sportspassport.kr/login/")
    assert (failure.value.status, failure.value.code) == (status, code)
    assert "sensitive" not in failure.value.message


def test_oauth_timeout_has_retryable_error(kakao, monkeypatch):
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("private request")

    monkeypatch.setattr(oauth.httpx, "post", timeout)
    with pytest.raises(ApiError) as failure:
        oauth.fetch_profile(AuthProvider.kakao, "code", "https://sportspassport.kr/login/")
    assert (failure.value.status, failure.value.code) == (503, "oauth_unavailable")


def test_authorize_config_errors_and_state_cookie_contract(kakao, monkeypatch):
    class Service:
        calls = 0

        async def oauth_login(self, provider, body):
            self.calls += 1
            return {"access_token": "test-only", "expires_in": 60, "user": {"id": 7, "email": "user@example.com"}}

    service = Service()
    app.dependency_overrides[get_auth_service] = lambda: service
    try:
        with TestClient(app, base_url="https://sportspassport.kr") as client:
            auth = client.get("/api/auth/oauth/kakao/authorize", params={"redirectUri": "https://sportspassport.kr/login/"})
            assert auth.status_code == 200
            assert "Secure" in auth.headers["set-cookie"]
            assert "HttpOnly" in auth.headers["set-cookie"]
            state = parse_qs(urlparse(auth.json()["authorizationUrl"]).query)["state"][0]
            body = {"code": "fake", "state": "wrong", "redirectUri": "https://sportspassport.kr/login/"}
            assert client.post("/api/auth/oauth/kakao/login", json=body).json()["error"] == "invalid_oauth_state"
            assert service.calls == 0
            for invalid_state in ("한글-state", "😀", "\ud800"):
                body["state"] = invalid_state
                invalid = client.post(
                    "/api/auth/oauth/kakao/login",
                    content=json.dumps(body),
                    headers={"Content-Type": "application/json"},
                )
                assert invalid.status_code == 400
                expected_error = "invalid_request" if invalid_state == "\ud800" else "invalid_oauth_state"
                assert invalid.json()["error"] == expected_error
                assert service.calls == 0
            body["state"] = state
            assert client.post("/api/auth/oauth/kakao/login", json=body).status_code == 200
            assert service.calls == 1
            # The cookie is consumed, so replay cannot invoke the provider again.
            assert client.post("/api/auth/oauth/kakao/login", json=body).json()["error"] == "invalid_oauth_state"
            assert service.calls == 1
            monkeypatch.delenv("KAKAO_CLIENT_ID")
            missing = client.get("/api/auth/oauth/kakao/authorize", params={"redirectUri": "https://sportspassport.kr/login/"})
            assert missing.status_code == 503
            assert missing.json()["error"] == "oauth_not_configured"
    finally:
        app.dependency_overrides.pop(get_auth_service, None)


def test_google_token_exchange_still_requires_secret(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    with pytest.raises(ApiError) as failure:
        oauth.fetch_profile(AuthProvider.google, "code", "https://sportspassport.kr/login/")
    assert failure.value.code == "oauth_not_configured"
