import os
from urllib.parse import urlencode, urlparse

import httpx

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
        "scope": "account_email",
    },
}


def _config(provider: AuthProvider) -> dict[str, str]:
    config = PROVIDERS[provider]
    client_id = os.getenv(config["client_id_env"])
    client_secret = os.getenv(config["client_secret_env"])
    if not client_id or not client_secret:
        raise RuntimeError(
            f"{config['client_id_env']} and {config['client_secret_env']} are required."
        )
    return {**config, "client_id": client_id, "client_secret": client_secret}


def is_allowed_redirect_uri(uri: str) -> bool:
    parsed = urlparse(uri)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    allowed = [value.strip() for value in os.getenv("AUTH_ALLOWED_REDIRECT_URIS", "").split(",") if value.strip()]
    return uri in allowed if allowed else os.getenv("ENVIRONMENT") != "production"


def authorization_url(provider: AuthProvider, redirect_uri: str, state: str) -> str:
    config = _config(provider)
    query = urlencode(
        {
            "client_id": config["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "scope": config["scope"],
        }
    )
    return f"{config['authorization_url']}?{query}"


def fetch_profile(provider: AuthProvider, code: str, redirect_uri: str) -> tuple[str, str | None]:
    config = _config(provider)
    token_response = httpx.post(
        config["token_url"],
        data={
            "grant_type": "authorization_code",
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=10,
    )
    token_response.raise_for_status()
    access_token = token_response.json().get("access_token")
    if not isinstance(access_token, str):
        raise RuntimeError(f"Invalid {provider.value} token response.")
    profile_response = httpx.get(
        config["profile_url"],
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    profile_response.raise_for_status()
    profile = profile_response.json()
    if provider is AuthProvider.google:
        provider_id, email = profile.get("sub"), profile.get("email")
        if profile.get("email_verified") is not True:
            email = None
    else:
        provider_id = profile.get("id")
        account = profile.get("kakao_account", {})
        email = account.get("email")
        if not account.get("is_email_valid") or not account.get("is_email_verified"):
            email = None
    if not isinstance(provider_id, (str, int)) or str(provider_id) == "":
        raise RuntimeError(f"Missing required {provider.value} profile id.")
    return str(provider_id), email if isinstance(email, str) and "@" in email else None
