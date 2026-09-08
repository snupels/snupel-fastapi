import os
from urllib.parse import urlencode, urlparse

import httpx

from app.exceptions import ApiError
from app.schemas.auth import AuthProvider

PROVIDERS = {
    AuthProvider.google: {
        "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "profile_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "client_id_env": "GOOGLE_CLIENT_ID",
        "client_secret_env": "GOOGLE_CLIENT_SECRET",
        "scope": "openid email profile",
    },
    AuthProvider.kakao: {
        "authorization_url": "https://kauth.kakao.com/oauth/authorize",
        "token_url": "https://kauth.kakao.com/oauth/token",
        "profile_url": "https://kapi.kakao.com/v2/user/me",
        "client_id_env": "KAKAO_CLIENT_ID",
        "client_secret_env": "KAKAO_CLIENT_SECRET",
        # The existing Kakao app is not a business app, so account_email is not
        # available. A stable provider id is sufficient for account creation;
        # the user completes nickname/profile details in our onboarding flow.
        "scope": "",
    },
}


def _config(provider: AuthProvider, *, for_token: bool = False) -> dict[str, str]:
    config = PROVIDERS[provider]
    client_id = os.getenv(config["client_id_env"], "").strip()
    client_secret = os.getenv(config["client_secret_env"], "").strip()
    # Kakao only requires a secret when it is enabled in the provider console.
    # A secret is never sent to the browser's authorization endpoint.
    if not client_id or (for_token and provider is AuthProvider.google and not client_secret):
        raise ApiError(503, "oauth_not_configured", "Social login configuration is unavailable.")
    return {**config, "client_id": client_id, "client_secret": client_secret}


def _provider_json(response: httpx.Response) -> dict:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        try:
            body = response.json()
        except ValueError:
            body = {}
        body = body if isinstance(body, dict) else {}
        # Never forward provider bodies: they can contain request credentials.
        if body.get("error") == "invalid_client" or body.get("error_code") in {
            "KOE101", "KOE010", "KOE004", "KOE006", "KOE303", "KOE322"
        }:
            raise ApiError(503, "oauth_not_configured", "Social login configuration is unavailable.") from None
        if body.get("error") == "invalid_grant" or body.get("error_code") == "KOE320":
            raise ApiError(400, "oauth_code_expired", "Social login authorization has expired. Start again.") from None
        raise ApiError(502, "oauth_unavailable", "Social login provider is temporarily unavailable.") from None
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise ApiError(502, "oauth_unavailable", "Invalid social login provider response.")
    return body


def is_allowed_redirect_uri(uri: str) -> bool:
    parsed = urlparse(uri)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    allowed = [value.strip() for value in os.getenv("AUTH_ALLOWED_REDIRECT_URIS", "").split(",") if value.strip()]
    return uri in allowed if allowed else os.getenv("ENVIRONMENT") != "production"


def authorization_url(provider: AuthProvider, redirect_uri: str, state: str) -> str:
    config = _config(provider)
    params = {
        "client_id": config["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    }
    if config["scope"]:
        params["scope"] = config["scope"]
    query = urlencode(params)
    return f"{config['authorization_url']}?{query}"


def fetch_profile(provider: AuthProvider, code: str, redirect_uri: str) -> tuple[str, str | None]:
    config = _config(provider, for_token=True)
    try:
        return _fetch_profile(config, provider, code, redirect_uri)
    except httpx.RequestError:
        raise ApiError(503, "oauth_unavailable", "Social login provider is temporarily unavailable.") from None


def _fetch_profile(config: dict[str, str], provider: AuthProvider, code: str, redirect_uri: str) -> tuple[str, str | None]:
    data = {
        "grant_type": "authorization_code",
        "client_id": config["client_id"],
        "redirect_uri": redirect_uri,
        "code": code,
    }
    if config["client_secret"]:
        data["client_secret"] = config["client_secret"]
    token_response = httpx.post(
        config["token_url"],
        data=data,
        timeout=10,
    )
    access_token = _provider_json(token_response).get("access_token")
    if not isinstance(access_token, str):
        raise ApiError(502, "oauth_unavailable", "Invalid social login provider response.")
    profile_response = httpx.get(
        config["profile_url"],
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    profile = _provider_json(profile_response)
    if provider is AuthProvider.google:
        provider_id, email = profile.get("sub"), profile.get("email")
        if profile.get("email_verified") is not True:
            email = None
    else:
        provider_id = profile.get("id")
        account = profile.get("kakao_account") or {}
        account = account if isinstance(account, dict) else {}
        email = account.get("email")
        if not account.get("is_email_valid") or not account.get("is_email_verified"):
            email = None
    if not isinstance(provider_id, (str, int)) or str(provider_id) == "":
        raise ApiError(502, "oauth_unavailable", "Invalid social login provider response.")
    return str(provider_id), email if isinstance(email, str) and "@" in email else None
