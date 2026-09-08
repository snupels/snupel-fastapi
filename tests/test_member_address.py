import asyncio
import importlib.util
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.admin import UserAdmin
from app.deps.auth import LoginUser, sign_access_token
from app.main import app
from app.models import Passport, SocialAccount, User
from app.repositories.auth import AuthRepository
from app.routes.auth import rate_limit
from app.schemas.auth import AuthProvider, OAuthLoginRequest, ProfileUpdateRequest, SignupRequest
from app.services.auth import AuthService, get_auth_service
from app.services.oauth import PROVIDERS
from app.services.stamp_submission import StampSubmissionService, get_stamp_submission_service


SIGNUP = {
    "email": "member@example.com", "password": "password123", "nickname": "강원회원",
    "phoneNumber": "01012345678", "agreeTerms": True, "agreePrivacy": True,
}
ADDRESS = {"postalCode": "  24300 ", "address": " 강원특별자치도 춘천시 테스트길 1 ", "addressDetail": " 101호 "}
NORMALIZED = {"postal_code": "24300", "address": "강원특별자치도 춘천시 테스트길 1", "address_detail": "101호"}


@pytest.fixture
def repository():
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    for model in (User, Passport, SocialAccount):
        table = model.__table__.to_metadata(metadata)
        # SQLite auto-increment requires INTEGER PRIMARY KEY, unlike MySQL BIGINT.
        table.c.id.type = sa.Integer()
        # MySQL's ON UPDATE timestamp clause is not part of SQLite's DDL.
        table.c.updated_at.server_default = sa.DefaultClause(sa.text("CURRENT_TIMESTAMP"))
    metadata.create_all(engine)
    with Session(engine) as session:
        class AsyncAdapter:
            add = session.add

            async def flush(self):
                session.flush()

            async def refresh(self, row):
                session.refresh(row)

            async def scalar(self, query):
                return session.scalar(query)

            async def get(self, model, item_id):
                return session.get(model, item_id)

        yield AuthRepository(AsyncAdapter()), session
    engine.dispose()


@pytest.mark.parametrize("model", [SignupRequest, ProfileUpdateRequest])
def test_optional_address_normalization_and_post_trim_limits(model):
    required = SIGNUP if model is SignupRequest else {}
    body = model(**(required | ADDRESS))
    assert {key: getattr(body, key) for key in NORMALIZED} == NORMALIZED
    assert set(NORMALIZED) <= body.model_fields_set
    omitted = model(**required)
    assert not set(NORMALIZED) & omitted.model_fields_set
    for fields in ({"postalCode": " ", "address": " \n", "addressDetail": "\t"},
                   {"postalCode": None, "address": None, "addressDetail": None}):
        cleared = model(**(required | fields))
        assert all(getattr(cleared, key) is None for key in NORMALIZED)
        assert set(NORMALIZED) <= cleared.model_fields_set
    maximum = model(**(required | {"address": " " + "가" * 500 + " ", "addressDetail": " " + "나" * 200 + " "}))
    assert len(maximum.address) == 500
    assert len(maximum.address_detail) == 200


@pytest.mark.parametrize("model", [SignupRequest, ProfileUpdateRequest])
@pytest.mark.parametrize("invalid", [
    {"postalCode": "1234"}, {"postalCode": "123456"}, {"postalCode": "12 45"},
    {"postalCode": "１２３４５"}, {"postalCode": "١٢٣٤٥"}, {"postalCode": 12345},
    {"address": "가" * 501}, {"addressDetail": "나" * 201}, {"address": ["주소"]},
])
def test_invalid_address_is_rejected(model, invalid):
    with pytest.raises(ValidationError):
        model(**((SIGNUP if model is SignupRequest else {}) | invalid))


@pytest.mark.parametrize("address_fields", [{}, ADDRESS])
def test_signup_persists_optional_address_and_returns_only_self_fields(repository, monkeypatch, address_fields):
    repo, session = repository
    monkeypatch.setenv("JWT_SECRET", "address-tests-secret")
    monkeypatch.setattr("app.services.auth.password_hasher", SimpleNamespace(hash=lambda _: "test-hash"))
    result = asyncio.run(AuthService(repo).signup(SignupRequest(**(SIGNUP | address_fields))))
    session.expire_all()
    saved = session.get(User, result.user.id)
    expected = NORMALIZED if address_fields else dict.fromkeys(NORMALIZED)
    assert {key: getattr(saved, key) for key in NORMALIZED} == expected
    public = result.user.model_dump(by_alias=True)
    assert {key: public[key] for key in ("postalCode", "address", "addressDetail")} == {
        "postalCode": expected["postal_code"], "address": expected["address"],
        "addressDetail": expected["address_detail"],
    }
    assert public["onboardingRequired"] is False
    assert "postal_code" not in public and "address_detail" not in public
    assert session.scalar(sa.select(sa.func.count()).select_from(Passport)) == 1


def test_own_profile_patch_omit_update_and_clear_are_persisted(repository):
    repo, session = repository
    user = asyncio.run(repo.create_user(email=SIGNUP["email"], password_hash=None, **NORMALIZED))
    actor, service = LoginUser(user.id, user.email), AuthService(repo)
    asyncio.run(service.update_profile(actor, ProfileUpdateRequest(nickname="새닉네임")))
    session.expire_all()
    assert {key: getattr(user, key) for key in NORMALIZED} == NORMALIZED
    asyncio.run(service.update_profile(actor, ProfileUpdateRequest(addressDetail=" 202호 ")))
    session.expire_all()
    assert user.address_detail == "202호" and user.postal_code == "24300"
    asyncio.run(service.update_profile(actor, ProfileUpdateRequest(postalCode=" ", address=None, addressDetail="")))
    session.expire_all()
    assert all(getattr(user, key) is None for key in NORMALIZED)


@pytest.mark.parametrize("with_address", [False, True])
def test_social_signup_onboarding_keeps_address_optional(repository, monkeypatch, with_address):
    repo, session = repository
    monkeypatch.setenv("JWT_SECRET", "address-tests-secret")
    monkeypatch.setenv("AUTH_ALLOWED_REDIRECT_URIS", "https://sportspassport.kr/login/")
    monkeypatch.setattr("app.services.auth.fetch_profile", lambda *_: ("provider-test", None))
    service = AuthService(repo)
    login = asyncio.run(service.oauth_login(AuthProvider.kakao, OAuthLoginRequest(
        code="test-code", state="test-state", redirectUri="https://sportspassport.kr/login/",
    )))
    assert login.user.onboarding_required is True
    assert login.user.address is None
    body = {"nickname": "소셜회원", "phoneNumber": "01012345678", "agreeTerms": True, "agreePrivacy": True}
    if with_address:
        body |= ADDRESS
    result = asyncio.run(service.update_profile(
        LoginUser(login.user.id, login.user.email), ProfileUpdateRequest(**body),
    ))
    assert result.onboarding_required is False
    session.expire_all()
    saved = session.get(User, result.id)
    assert saved.password_hash is None
    assert saved.address == (NORMALIZED["address"] if with_address else None)
    assert PROVIDERS[AuthProvider.kakao]["scope"] == ""
    assert PROVIDERS[AuthProvider.google]["scope"] == "openid email profile"


def complete_user(item_id=7, **fields):
    return SimpleNamespace(
        id=item_id, email=f"member{item_id}@example.com", nickname="테스트회원",
        phone_number="01012345678", terms_agreed_at=datetime.now(), privacy_agreed_at=datetime.now(),
        **(NORMALIZED | fields),
    )


def test_existing_member_without_address_does_not_require_onboarding():
    user = complete_user(**dict.fromkeys(NORMALIZED))
    assert AuthService(object())._user(user).onboarding_required is False


def test_self_profile_api_requires_auth_and_cannot_target_another_member(monkeypatch):
    users = {7: complete_user(), 8: complete_user(8, address="다른 회원의 비공개 주소")}

    class Repository:
        async def find_user_by_id(self, item_id):
            return users.get(item_id)

        async def update_profile(self, user, **values):
            for key, value in values.items():
                setattr(user, key, value)
            return user

    monkeypatch.setenv("JWT_SECRET", "address-tests-secret")
    service = AuthService(Repository())
    app.dependency_overrides[get_auth_service] = lambda: service
    app.dependency_overrides[rate_limit] = lambda: None
    try:
        with TestClient(app) as client:
            assert client.get("/api/auth/me").status_code == 401
            assert client.patch("/api/auth/me", json=ADDRESS).status_code == 401
            token = sign_access_token(LoginUser(7, users[7].email))[0]
            headers = {"Authorization": f"Bearer {token}"}
            own = client.get("/api/auth/me?user_id=8", headers=headers)
            assert own.status_code == 200 and own.json()["id"] == 7
            assert own.json()["address"] == NORMALIZED["address"]
            assert client.patch("/api/auth/me", headers=headers, json=ADDRESS | {"userId": 8}).status_code == 400
            updated = client.patch("/api/auth/me", headers=headers, json={"addressDetail": "303호"})
            assert updated.status_code == 200 and updated.json()["addressDetail"] == "303호"
            cleared = client.patch("/api/auth/me", headers=headers, json={"address": " ", "postalCode": None})
            assert cleared.status_code == 200 and cleared.json()["address"] is None
            private_input = "PRIVATE-ADDRESS-VALIDATION-SENTINEL" * 20
            invalid = client.patch("/api/auth/me", headers=headers, json={"address": private_input})
            invalid_signup = client.post("/api/auth/signup", json=SIGNUP | {"address": private_input})
            for response in (invalid, invalid_signup):
                assert response.status_code == 400
                assert response.json() == {"error": "invalid_request", "message": "Invalid request body."}
                assert "PRIVATE-ADDRESS-VALIDATION-SENTINEL" not in response.text
                assert response.headers["cache-control"] == "no-store"
            assert users[8].address == "다른 회원의 비공개 주소" and users[8].address_detail == "101호"
    finally:
        app.dependency_overrides.pop(get_auth_service, None)
        app.dependency_overrides.pop(rate_limit, None)


def test_public_profile_posts_and_comments_never_expose_member_address(monkeypatch):
    author = complete_user(address="PRIVATE-ADDRESS-SENTINEL", address_detail="PRIVATE-DETAIL-SENTINEL")
    post = SimpleNamespace(id=1, object_key="proofs/demo.jpg", feed_caption="공개 글", reviewed_at=datetime.now())
    comment = SimpleNamespace(id=1, content="공개 댓글", created_at=datetime.now())

    class Repository:
        async def public_profile(self, *_):
            return author, 0, 0, False

        async def list_feed(self, **_):
            return [(post, None, author)]

        async def visible_feed_item(self, *_):
            return post

        async def list_comments(self, *_, **__):
            return [(comment, author)]

        async def add_comment(self, *_):
            return comment, author

    service = StampSubmissionService(Repository(), SimpleNamespace(proof_url=lambda _: "https://example.com/public.jpg"))
    app.dependency_overrides[get_stamp_submission_service] = lambda: service
    monkeypatch.setenv("JWT_SECRET", "address-tests-secret")
    try:
        with TestClient(app) as client:
            paths = ["/api/community-profiles/7", "/api/community-feed", "/api/community-feed/posts/1",
                     "/api/community-feed/users/7", "/api/community-feed/1/comments"]
            responses = [client.get(path) for path in paths]
            token = sign_access_token(LoginUser(7, author.email))[0]
            responses.append(client.post("/api/community-feed/1/comments", json={"content": "댓글"},
                                         headers={"Authorization": f"Bearer {token}"}))
            for response in responses:
                assert response.status_code in {200, 201}, response.text
                assert "PRIVATE-ADDRESS-SENTINEL" not in response.text
                assert "PRIVATE-DETAIL-SENTINEL" not in response.text
                assert "postalCode" not in response.text and "postal_code" not in response.text
                assert "addressDetail" not in response.text and '"address"' not in response.text
    finally:
        app.dependency_overrides.pop(get_stamp_submission_service, None)


def test_member_address_is_not_added_to_general_admin_user_views():
    view = UserAdmin()
    private_fields = {"postal_code", "address", "address_detail", "password_hash"}
    assert not private_fields & set(view.get_list_columns())
    assert not private_fields & set(view.get_details_columns())
    assert not private_fields & set(view.get_form_columns())


def test_address_migration_keeps_existing_users_null(monkeypatch):
    path = Path("alembic/versions/0040_member_address.py")
    spec = importlib.util.spec_from_file_location("member_address_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE users (id INTEGER PRIMARY KEY, nickname VARCHAR(30))"))
        connection.execute(sa.text("INSERT INTO users VALUES (7, '기존회원')"))
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        row = connection.execute(sa.text("SELECT * FROM users")).mappings().one()
        assert row == {"id": 7, "nickname": "기존회원", "postal_code": None, "address": None, "address_detail": None}
        columns = {column["name"]: column for column in sa.inspect(connection).get_columns("users")}
        for key, length in (("postal_code", 5), ("address", 500), ("address_detail", 200)):
            assert columns[key]["nullable"] is True
            assert columns[key]["type"].length == length
    engine.dispose()
