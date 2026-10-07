import ssl
from types import SimpleNamespace

import pytest

from app.config import database_connect_args, database_url
from app.deps.rate_limit import RateLimiter
from app.schemas.auth import AuthProvider
from app.services import oauth


def test_rate_limiter_bounds_keys_and_requests():
    limiter = RateLimiter(limit=2, capacity=2)
    assert limiter.allow("a")
    assert limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")
    assert limiter.allow("c")
    assert list(limiter.buckets) == ["b", "c"]


def test_production_requires_database_url(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        database_url()


def test_oauth_ignores_unverified_provider_email(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    token = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"access_token": "token"})
    profile = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"sub": "7", "email": "admin@example.com", "email_verified": False},
    )
    monkeypatch.setattr(oauth.httpx, "post", lambda *args, **kwargs: token)
    monkeypatch.setattr(oauth.httpx, "get", lambda *args, **kwargs: profile)

    assert oauth.fetch_profile(AuthProvider.google, "code", "https://example.com/callback") == (
        "7",
        None,
    )


def test_systemd_services_drop_privileges():
    for path in ("deploy/snupel-fastapi.service", "deploy/snupel-tourism-sync.service"):
        service = open(path, encoding="utf-8").read()
        assert "NoNewPrivileges=true" in service
        assert "ProtectSystem=strict" in service
        assert "ProtectHome=read-only" in service
        assert "CapabilityBoundingSet=" in service


def test_database_tls_configuration(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("DATABASE_SSL_CA", raising=False)
    assert database_connect_args() == {}
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="DATABASE_SSL_CA is required"):
        database_connect_args()

    context = ssl.create_default_context()
    loaded = []
    monkeypatch.setattr(
        "app.config.ssl.create_default_context",
        lambda *, cafile: loaded.append(cafile) or context,
    )
    monkeypatch.setenv("DATABASE_SSL_CA", "/etc/ssl/rds-ca.pem")
    assert database_connect_args() == {"ssl": context}
    assert loaded == ["/etc/ssl/rds-ca.pem"]
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_database_tls_invalid_ca_fails_closed(monkeypatch, tmp_path):
    ca_file = tmp_path / "invalid.pem"
    ca_file.write_text("invalid certificate")
    monkeypatch.setenv("DATABASE_SSL_CA", str(ca_file))
    with pytest.raises(ssl.SSLError):
        database_connect_args()
