import asyncio
import importlib.util
import smtplib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from argon2.exceptions import VerifyMismatchError
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin import UserAdmin
from app.deps.auth import LoginUser, sign_access_token
from app.deps.rate_limit import RateLimiter
from app.exceptions import ApiError
from app.main import app
from app.models import Passport, PasswordResetCode, SocialAccount, User
from app.repositories.auth import AuthRepository
from app.routes import auth as auth_routes
from app.schemas.auth import (
    AuthProvider, LoginRequest, OAuthLoginRequest, PasswordResetConfirm,
    PasswordResetRequest, ProfileUpdateRequest, SignupRequest, UsernameAvailabilityQuery,
)
from app.services.auth import AuthService, get_auth_service


SIGNUP = {
    "username": "gangwon_user", "email": "member@example.com", "password": "password123",
    "nickname": "보이는닉네임", "phoneNumber": "01012345678", "agreeTerms": True, "agreePrivacy": True,
}


@pytest.fixture
def auth_environment(monkeypatch):
    def verify(encoded, password):
        if encoded != f"hashed:{password}":
            raise VerifyMismatchError()
        return True

    monkeypatch.setenv("JWT_SECRET", "username-auth-test-secret")
    monkeypatch.setattr("app.services.auth.password_hasher", SimpleNamespace(
        hash=lambda password: f"hashed:{password}", verify=verify,
    ))
    messages = []
    monkeypatch.setattr("app.services.auth.send_mail", lambda *message: messages.append(message))
    return messages


@pytest.fixture
def database():
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    for model in (User, Passport, SocialAccount, PasswordResetCode):
        table = model.__table__.to_metadata(metadata)
        table.c.id.type = sa.Integer()
        table.c.updated_at.server_default = sa.DefaultClause(sa.text("CURRENT_TIMESTAMP"))
    metadata.create_all(engine)
    with Session(engine) as session:
        class Adapter:
            add = session.add

            @asynccontextmanager
            async def begin_nested(self):
                with session.begin_nested() as transaction:
                    class AsyncTransaction:
                        async def rollback(self):
                            transaction.rollback()
                    yield AsyncTransaction()

            async def flush(self):
                session.flush()

            async def refresh(self, row):
                session.refresh(row)

            async def scalar(self, query):
                return session.scalar(query)

            async def get(self, model, item_id):
                return session.get(model, item_id)

            async def execute(self, query):
                return session.execute(query)

        yield AuthRepository(Adapter()), session
    engine.dispose()


@pytest.mark.parametrize("model", [SignupRequest, ProfileUpdateRequest, UsernameAvailabilityQuery])
def test_username_normalization_is_separate_from_nickname(model):
    fields = SIGNUP if model is SignupRequest else {}
    body = model(**(fields | {"username": "  Runner_2026  "}))
    assert body.username == "runner_2026"
    if model is SignupRequest:
        assert body.nickname == "보이는닉네임"


@pytest.mark.parametrize("username", ["abc", "a" * 21, "bad.name", "bad name", "test@a.kr", "강원회원", "Kaaa", "ＡＢＣＤ", "", "   ", 12345])
@pytest.mark.parametrize("model", [SignupRequest, ProfileUpdateRequest, UsernameAvailabilityQuery])
def test_username_rejects_non_ascii_invalid_length_and_characters(model, username):
    with pytest.raises(ValidationError):
        model(**((SIGNUP if model is SignupRequest else {}) | {"username": username}))


def test_signup_requires_username_but_profile_allows_omission():
    with pytest.raises(ValidationError):
        SignupRequest(**{key: value for key, value in SIGNUP.items() if key != "username"})
    assert "username" not in ProfileUpdateRequest(nickname="새닉네임").model_fields_set
    for body in ({"email": "member@example.com"}, {"username": "gangwon_user"}):
        with pytest.raises(ValidationError):
            PasswordResetRequest(**body)
    with pytest.raises(ValidationError):
        PasswordResetConfirm(email="member@example.com", code="123456", newPassword="password456")
    assert PasswordResetRequest(username=" MEMBER@EXAMPLE.COM ", email="member@example.com").username == "member@example.com"


def test_login_identifier_and_legacy_email_alias():
    assert LoginRequest(identifier="  RUNNER_2026 ", password="pw").identifier == "runner_2026"
    assert LoginRequest(email=" Member@Example.Com ", password="pw").identifier == "member@example.com"
    with pytest.raises(ValidationError):
        LoginRequest(identifier="runner_2026", email="member@example.com", password="pw")


def test_signup_username_email_login_and_distinct_duplicate_errors(database, auth_environment):
    repo, session = database
    service = AuthService(repo)
    response = asyncio.run(service.signup(SignupRequest(**(SIGNUP | {"username": " GANGWON_USER "}))))
    assert response.user.username == "gangwon_user"
    assert response.user.nickname == "보이는닉네임"
    assert response.user.onboarding_required is False
    session.expire_all()
    assert session.get(User, response.user.id).username == "gangwon_user"
    for body in (LoginRequest(identifier="GANGWON_USER", password="password123"),
                 LoginRequest(identifier=SIGNUP["email"], password="password123"),
                 LoginRequest(email=SIGNUP["email"], password="password123")):
        assert asyncio.run(service.login(body)).user.id == response.user.id
    for values, code in (({"username": "other_name"}, "email_already_exists"),
                         ({"email": "other@example.com"}, "username_already_exists")):
        with pytest.raises(ApiError) as error:
            asyncio.run(service.signup(SignupRequest(**(SIGNUP | values))))
        assert error.value.code == code
    assert session.scalar(sa.select(sa.func.count()).select_from(Passport)) == 1


def test_legacy_email_login_and_existing_onboarding_remain_unchanged(database, auth_environment):
    repo, _ = database
    user = asyncio.run(repo.create_user(
        email="legacy@example.com", password_hash="hashed:password123", nickname="기존회원",
        phone_number="01012345678", terms_agreed_at=datetime.now(), privacy_agreed_at=datetime.now(),
    ))
    result = asyncio.run(AuthService(repo).login(LoginRequest(email="LEGACY@EXAMPLE.COM", password="password123")))
    assert result.user.id == user.id and result.user.username is None
    assert result.user.onboarding_required is False
    with pytest.raises(ApiError) as error:
        asyncio.run(AuthService(repo).login(LoginRequest(identifier="legacy@example.com", password="wrong")))
    assert error.value.code == "invalid_credentials"


def test_profile_username_assigns_once_and_omitted_or_same_value_is_safe(database, auth_environment):
    repo, session = database
    user = asyncio.run(repo.create_user(email="social@example.com", password_hash=None))
    actor = LoginUser(user.id, user.email)
    service = AuthService(repo)
    first = asyncio.run(service.update_profile(actor, ProfileUpdateRequest(username=" Social_User ")))
    assert first.username == "social_user"
    same = asyncio.run(service.update_profile(actor, ProfileUpdateRequest(username=" SOCIAL_USER ", nickname="새닉네임")))
    assert same.username == "social_user" and same.nickname == "새닉네임"
    asyncio.run(service.update_profile(actor, ProfileUpdateRequest(address="춘천시")))
    for requested in ("different_user", None):
        with pytest.raises(ApiError) as error:
            asyncio.run(service.update_profile(actor, ProfileUpdateRequest(username=requested)))
        assert error.value.code == "username_change_not_allowed"
    session.expire_all()
    assert user.username == "social_user" and user.address == "춘천시"


def test_username_assignment_locks_and_refreshes_the_owner_row():
    queries = []

    class Session:
        async def scalar(self, query):
            queries.append(query)
            return None

    asyncio.run(AuthRepository(Session()).find_user_by_id(7, lock=True))
    assert "FOR UPDATE" in str(queries[0].compile(dialect=mysql.dialect()))
    assert queries[0].get_execution_options()["populate_existing"] is True


@pytest.mark.parametrize(("conflict", "expected"), [("username", "username_already_exists"), ("email", "email_already_exists")])
def test_signup_database_unique_race_is_reported_without_database_details(database, auth_environment, conflict, expected):
    repo, session = database
    asyncio.run(repo.create_user(email=SIGNUP["email"], password_hash=None, username=SIGNUP["username"]))
    session.commit()

    class RaceRepository(AuthRepository):
        async def find_user_by_email(self, _):
            return None

        async def find_user_by_username(self, _):
            return None

    fields = SIGNUP | ({"email": "other@example.com"} if conflict == "username" else {"username": "another_user"})
    with pytest.raises(ApiError) as error:
        asyncio.run(AuthService(RaceRepository(repo.session)).signup(SignupRequest(**fields)))
    assert error.value.code == expected
    assert "UNIQUE" not in error.value.message and "example.com" not in error.value.message
    session.rollback()
    assert session.scalar(sa.select(sa.func.count()).select_from(User)) == 1
    assert session.scalar(sa.select(sa.func.count()).select_from(Passport)) == 1


def test_profile_database_unique_race_cannot_claim_another_users_username(database, auth_environment):
    repo, session = database
    owner = asyncio.run(repo.create_user(email="owner@example.com", password_hash=None))
    taken = asyncio.run(repo.create_user(email="other@example.com", password_hash=None, username="taken_user"))
    session.commit()

    class RaceRepository(AuthRepository):
        async def find_user_by_username(self, _):
            return None

    actor = LoginUser(owner.id, owner.email)
    with pytest.raises(ApiError) as error:
        asyncio.run(AuthService(RaceRepository(repo.session)).update_profile(actor, ProfileUpdateRequest(username="taken_user")))
    assert error.value.code == "username_already_exists"
    session.rollback()
    assert owner.username is None and taken.username == "taken_user"


def test_oauth_registration_and_one_time_username_onboarding(database, auth_environment, monkeypatch):
    repo, _ = database
    monkeypatch.setenv("AUTH_ALLOWED_REDIRECT_URIS", "https://sportspassport.kr/login/")
    monkeypatch.setattr("app.services.auth.fetch_profile", lambda *_: ("kakao-unique-user", "social@example.com"))
    service = AuthService(repo)
    body = OAuthLoginRequest(code="code", state="state", redirectUri="https://sportspassport.kr/login/")
    first = asyncio.run(service.oauth_login(AuthProvider.kakao, body))
    assert first.user.username is None and first.user.onboarding_required is True
    updated = asyncio.run(service.update_profile(LoginUser(first.user.id, first.user.email), ProfileUpdateRequest(
        username="social_member", nickname="소셜회원", phoneNumber="01012345678", agreeTerms=True, agreePrivacy=True,
    )))
    assert updated.username == "social_member" and updated.onboarding_required is False
    repeated = asyncio.run(service.oauth_login(AuthProvider.kakao, body))
    assert repeated.user.id == first.user.id and repeated.user.username == "social_member"


@pytest.mark.parametrize("legacy", [False, True])
def test_password_reset_requires_same_username_email_pair_in_request_and_confirm(database, auth_environment, monkeypatch, legacy):
    repo, session = database
    username = None if legacy else "actual_user"
    user = asyncio.run(repo.create_user(email="reset@example.com", password_hash="hashed:old-password", username=username))
    service = AuthService(repo)
    identifier = username or user.email
    monkeypatch.setattr("app.services.auth.secrets.randbelow", lambda _: 123456)
    for email, requested in ((user.email, "wrong_user"), ("different@example.com", identifier)):
        asyncio.run(service.request_password_reset(email, requested))
    if not legacy:
        asyncio.run(service.request_password_reset(user.email, user.email))
    assert session.scalar(sa.select(sa.func.count()).select_from(PasswordResetCode)) == 0
    assert not auth_environment
    asyncio.run(service.request_password_reset(user.email, identifier.upper()))
    assert len(auth_environment) == 1 and "123456" in auth_environment[0][2]
    for requested in ("wrong_user", "유니코드", user.email if not legacy else "different@example.com"):
        with pytest.raises(ApiError) as error:
            asyncio.run(service.confirm_password_reset(PasswordResetConfirm(
                username=requested, email=user.email, code="123456", newPassword="new-password",
            )))
        assert error.value.code == "invalid_reset_code"
        assert user.password_hash == "hashed:old-password"
    confirm = PasswordResetConfirm(username=identifier, email=user.email, code="123456", newPassword="new-password")
    asyncio.run(service.confirm_password_reset(confirm))
    assert user.password_hash == "hashed:new-password"
    assert session.scalar(sa.select(PasswordResetCode)).used_at is not None
    with pytest.raises(ApiError) as error:
        asyncio.run(service.confirm_password_reset(confirm))
    assert error.value.code == "invalid_reset_code"


def test_social_only_accounts_never_gain_password_through_recovery(database, auth_environment):
    repo, session = database
    user = asyncio.run(repo.create_user(email="social@example.com", password_hash=None, username="social_member"))
    service = AuthService(repo)
    asyncio.run(service.request_password_reset(user.email, "social_member"))
    assert session.scalar(sa.select(sa.func.count()).select_from(PasswordResetCode)) == 0
    assert len(auth_environment) == 1 and "소셜 로그인" in auth_environment[0][2]
    asyncio.run(repo.create_reset_code(user_id=user.id, code_hash=service._code_hash(user.email, "123456"), expires_at=datetime.now() + timedelta(minutes=10)))
    with pytest.raises(ApiError) as error:
        asyncio.run(service.confirm_password_reset(PasswordResetConfirm(
            username="social_member", email=user.email, code="123456", newPassword="new-password",
        )))
    assert error.value.code == "invalid_reset_code" and user.password_hash is None


@pytest.mark.parametrize("mail_error", [KeyError("MAIL_FROM"), smtplib.SMTPException("transport failure")])
def test_failed_reset_resend_preserves_previously_delivered_code(database, auth_environment, monkeypatch, mail_error):
    repo, session = database
    user = asyncio.run(repo.create_user(email="reset@example.com", password_hash="hashed:old-password", username="actual_user"))
    service = AuthService(repo)
    old_code = asyncio.run(repo.create_reset_code(
        user_id=user.id, code_hash=service._code_hash(user.email, "111111"),
        expires_at=datetime.now() + timedelta(minutes=10),
    ))
    session.commit()

    def failed_mail(*_):
        raise mail_error

    monkeypatch.setattr("app.services.auth.send_mail", failed_mail)
    monkeypatch.setattr("app.services.auth.secrets.randbelow", lambda _: 123456)
    asyncio.run(service.request_password_reset(user.email, user.username))
    session.commit()
    session.expire_all()
    assert session.scalar(sa.select(sa.func.count()).select_from(PasswordResetCode)) == 1
    assert old_code.used_at is None
    asyncio.run(service.confirm_password_reset(PasswordResetConfirm(
        username=user.username, email=user.email, code="111111", newPassword="new-password",
    )))
    assert user.password_hash == "hashed:new-password"


@pytest.mark.parametrize("username", [None, "actual_member"])
def test_account_reminder_emails_username_or_legacy_login_identifier(database, auth_environment, username):
    repo, _ = database
    user = asyncio.run(repo.create_user(email="remind@example.com", password_hash="hashed:pw", username=username))
    asyncio.run(AuthService(repo).account_reminder("REMIND@EXAMPLE.COM"))
    assert len(auth_environment) == 1
    assert auth_environment[0][0] == user.email
    assert f"로그인 아이디는 {username or user.email}" in auth_environment[0][2]


@pytest.fixture
def api_service(auth_environment):
    user = SimpleNamespace(id=7, email="private@example.com", username="taken_user", password_hash="hashed:password123", nickname="비공개회원")
    created_codes = []

    class Repository:
        @asynccontextmanager
        async def reset_code_transaction(self):
            prior = list(created_codes)

            class Transaction:
                async def rollback(self):
                    created_codes[:] = prior
            yield Transaction()

        async def find_user_by_email(self, email):
            return user if email == user.email else None

        async def find_user_by_username(self, username):
            return user if username == user.username else None

        async def find_user_by_id(self, item_id, **_):
            return user if item_id == user.id else None

        async def create_reset_code(self, **values):
            created_codes.append(values)

        async def active_reset_code(self, _):
            return None

        async def update_profile(self, row, **values):
            for key, value in values.items():
                setattr(row, key, value)
            return row

    app.dependency_overrides[get_auth_service] = lambda: AuthService(Repository())
    app.dependency_overrides[auth_routes.rate_limit] = lambda: None
    try:
        yield user, created_codes
    finally:
        app.dependency_overrides.pop(get_auth_service, None)
        app.dependency_overrides.pop(auth_routes.rate_limit, None)


def test_username_availability_query_is_normalized_limited_and_returns_no_pii(api_service, monkeypatch):
    with TestClient(app) as client:
        for value, expected in ((" Taken_User ", False), ("New_User", True)):
            response = client.get("/api/auth/username-availability", params={"username": value})
            assert response.status_code == 200
            assert response.json() == {"username": value.strip().lower(), "available": expected}
            assert response.headers["cache-control"] == "no-store"
            assert "private@example.com" not in response.text
        for value in ("bad.name", "가나다라", "aaa", "Kaaa"):
            assert client.get("/api/auth/username-availability", params={"username": value}).status_code == 400
        app.dependency_overrides.pop(auth_routes.rate_limit, None)
        monkeypatch.setattr(auth_routes, "rate_limiter", RateLimiter(2))
        statuses = [client.get("/api/auth/username-availability", params={"username": "test_user"}).status_code for _ in range(3)]
        assert statuses == [200, 200, 429]


def test_login_router_accepts_new_and_legacy_inputs_with_generic_failures(api_service):
    with TestClient(app) as client:
        for body in ({"identifier": "TAKEN_USER"}, {"identifier": "private@example.com"}, {"email": "private@example.com"}):
            result = client.post("/api/auth/login", json=body | {"password": "password123"})
            assert result.status_code == 200 and result.json()["user"]["username"] == "taken_user"
        errors = [client.post("/api/auth/login", json={"identifier": identifier, "password": "wrong"}) for identifier in ("taken_user", "not_registered")]
        assert all(response.status_code == 400 for response in errors)
        assert errors[0].json() == errors[1].json()


def test_profile_username_api_is_owner_only_and_rejects_change_or_clear(api_service):
    user, _ = api_service
    with TestClient(app) as client:
        assert client.patch("/api/auth/me", json={"username": "new_name"}).status_code == 401
        token = sign_access_token(LoginUser(user.id, user.email))[0]
        headers = {"Authorization": f"Bearer {token}"}
        same = client.patch("/api/auth/me", headers=headers, json={"username": " TAKEN_USER "})
        assert same.status_code == 200 and same.json()["username"] == "taken_user"
        for value in (None, "changed_name"):
            response = client.patch("/api/auth/me", headers=headers, json={"username": value})
            assert response.status_code == 400 and response.json()["error"] == "username_change_not_allowed"
        assert client.patch("/api/auth/me", headers=headers, json={"username": "new_name", "userId": 8}).status_code == 400


def test_recovery_routes_remain_generic_and_bind_username_at_confirmation(api_service, monkeypatch, caplog):
    user, created_codes = api_service

    def failed_mail(*_):
        raise smtplib.SMTPException("sensitive transport details must not be logged")

    monkeypatch.setattr("app.services.auth.send_mail", failed_mail)
    with TestClient(app) as client:
        requests = [
            {"username": user.username, "email": user.email},
            {"username": "wrong_name", "email": user.email},
            {"username": user.username, "email": "unknown@example.com"},
            {"username": user.email, "email": user.email},
        ]
        responses = [client.post("/api/auth/password-reset/request", json=body) for body in requests]
        assert all(response.status_code == 200 for response in responses)
        assert all(response.json() == responses[0].json() for response in responses)
        assert not created_codes
        assert all(response.headers["cache-control"] == "no-store" for response in responses)
        confirmed = [client.post("/api/auth/password-reset/confirm", json=body | {"code": "123456", "newPassword": "new-password"}) for body in requests]
        assert all(response.status_code == 400 for response in confirmed)
        assert all(response.json() == confirmed[0].json() for response in confirmed)
        missing_pair = client.post("/api/auth/password-reset/confirm", json={"email": user.email, "code": "123456", "newPassword": "new-password"})
        assert missing_pair.status_code == 400
        reminder = [client.post("/api/auth/account-reminder", json={"email": email}) for email in (user.email, "unknown@example.com")]
        assert all(response.status_code == 200 for response in reminder)
        assert reminder[0].json() == reminder[1].json()
    assert user.email not in caplog.text
    assert "sensitive transport details" not in caplog.text


def test_username_schema_is_nullable_unique_and_migration_does_not_backfill(database, monkeypatch):
    repo, session = database
    first = asyncio.run(repo.create_user(email="legacy1@example.com", password_hash=None))
    second = asyncio.run(repo.create_user(email="legacy2@example.com", password_hash=None))
    session.commit()
    assert first.username is None and second.username is None
    asyncio.run(repo.update_profile(first, username="unique_user"))
    session.commit()
    with pytest.raises(IntegrityError):
        asyncio.run(repo.update_profile(second, username="unique_user"))
    session.rollback()
    assert second.username is None
    path = Path("alembic/versions/0041_member_username.py")
    spec = importlib.util.spec_from_file_location("member_username_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    columns, constraints = [], []
    monkeypatch.setattr(migration.op, "add_column", lambda table, column: columns.append((table, column)))
    monkeypatch.setattr(migration.op, "create_unique_constraint", lambda *args: constraints.append(args))
    migration.upgrade()
    assert len(columns) == 1 and columns[0][0] == "users"
    assert columns[0][1].name == "username" and columns[0][1].nullable is True
    assert columns[0][1].type.length == 20
    assert constraints == [("users_username_unique", "users", ["username"])]
    assert "username" not in UserAdmin().get_form_columns()
