from app.deps.auth import LoginUser, access_token_expires_in, sign_access_token, verify_access_token


def test_signs_verifies_and_rejects_tokens(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.delenv("AUTH_ACCESS_TOKEN_EXPIRES_IN", raising=False)
    token, expires_in = sign_access_token(LoginUser(7, "user@example.com"), now=1_700_000_000)

    assert expires_in == 60 * 60 * 24 * 7
    assert verify_access_token(token, now=1_700_000_001) == LoginUser(7, "user@example.com")
    assert verify_access_token("not-a-token", now=1_700_000_001) is None
    assert verify_access_token(f"{token[:-1]}x", now=1_700_000_001) is None


def test_configured_expiry(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("AUTH_ACCESS_TOKEN_EXPIRES_IN", "2")
    token, expires_in = sign_access_token(LoginUser(7, "user@example.com"), now=1_700_000_000)

    assert access_token_expires_in() == expires_in == 2
    assert verify_access_token(token, now=1_700_000_003) is None
