import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import mysql

from app.deps.auth import LoginUser, optional_user, require_user
from app.exceptions import ApiError
from app.routes.stamp_submission import router
from app.services.stamp_submission import StampSubmissionService, get_stamp_submission_service
from app.repositories.stamp_submission import StampSubmissionRepository
from scripts.seed_community_demo import seed_demo


def test_follow_service_privacy_and_guards(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "operator@example.test")
    class Repo:
        followed = False
        async def public_profile(self, user_id, viewer_id):
            if user_id == 99:
                return None
            return SimpleNamespace(id=user_id, nickname="운영자", email="operator@example.test", profile_image_key=None), int(self.followed), 0, self.followed
        async def set_follow(self, actor, target, following):
            self.followed = following
    service = StampSubmissionService(Repo(), None)
    actor = LoginUser(1, "viewer@example.test")
    for value in [True, True, False, False]:
        result = asyncio.run(service.follow_user(2, actor, following=value))
        assert result["followed_by_me"] == value
        assert result["follower_count"] == int(value)
        assert "email" not in result and result["is_operator"]
    with pytest.raises(ApiError):
        asyncio.run(service.follow_user(1, actor, following=True))
    with pytest.raises(ApiError):
        asyncio.run(service.follow_user(99, actor, following=True))
    with pytest.raises(ApiError):
        asyncio.run(service.list_feed(following_only=True))


def test_follow_routes_auth_validation_and_contract():
    app = FastAPI()
    app.include_router(router)
    class Service:
        async def community_profile(self, user_id, actor):
            return {"id": user_id, "name": "공개닉네임", "profile_image_url": None,
                    "follower_count": 0, "following_count": 0, "followed_by_me": False, "is_operator": False}
        async def follow_user(self, user_id, actor, following):
            result = await self.community_profile(user_id, actor)
            return result | {"followed_by_me": following, "follower_count": int(following)}
    app.dependency_overrides[get_stamp_submission_service] = lambda: Service()
    app.dependency_overrides[optional_user] = lambda: None
    client = TestClient(app)
    assert client.get("/api/community-profiles/2").json()["name"] == "공개닉네임"
    assert client.get("/api/community-profiles/0").status_code == 422
    # Authentication dependency is deliberately not overridden for this request.
    with pytest.raises(ApiError):
        client.post("/api/community-profiles/2/follow")
    app.dependency_overrides[require_user] = lambda: LoginUser(1, "test@example.test")
    assert client.post("/api/community-profiles/2/follow").json()["followedByMe"] is True
    assert client.delete("/api/community-profiles/2/follow").json()["followedByMe"] is False


def test_following_feed_filters_authors_and_preserves_visibility():
    class Session:
        async def execute(self, query):
            sql = str(query.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))
            assert "user_follows.follower_id = 7" in sql
            assert "user_follows.followed_id = users.id" in sql
            assert "stamp_submissions.share_to_feed IS true" in sql
            assert "approved" in sql and "LEFT OUTER JOIN" in sql
            return SimpleNamespace(all=lambda: [])
    asyncio.run(StampSubmissionRepository(Session()).list_feed(viewer_user_id=7, following_only=True))


def test_demo_seed_is_idempotent_and_never_awards_stamps():
    with create_engine("sqlite://").begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)"))
        connection.execute(text("INSERT INTO users VALUES (7, 'operator@example.test')"))
        connection.execute(text("CREATE TABLE stamp_submissions (id INTEGER PRIMARY KEY, passport_id INTEGER, stamp_id INTEGER, author_id INTEGER, is_demo INTEGER, object_key TEXT, share_to_feed INTEGER, feed_caption TEXT, status TEXT, reviewer_id INTEGER, reviewed_at TEXT, created_at TEXT, updated_at TEXT)"))
        assert seed_demo(connection, {"operator@example.test"}) == "created"
        assert seed_demo(connection, {"operator@example.test"}) == "already_exists"
        row = connection.execute(text("SELECT * FROM stamp_submissions")).mappings().one()
        assert row["passport_id"] is None and row["stamp_id"] is None
        assert row["author_id"] == 7 and row["is_demo"] == 1
        assert "[운영자 데모]" in row["feed_caption"]
        assert "이 게시글은 기능 체험용 안내" not in row["feed_caption"]


def test_demo_response_uses_no_storage_or_fake_activity():
    row = SimpleNamespace(id=1, is_demo=True, feed_caption="데모", reviewed_at=datetime.now())
    author = SimpleNamespace(id=7, nickname="운영자", profile_image_key=None)
    response = asyncio.run(StampSubmissionService(None, None)._feed_response(
        row, None, author, engagement_values=(0, 0, False)
    ))
    assert response["is_demo"] and response["place_name"] is None
    assert response["proof_url"].endswith("community-demo.svg")
