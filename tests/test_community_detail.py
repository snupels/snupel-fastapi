import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from sqlalchemy.dialects import mysql

from app.deps.auth import LoginUser, optional_user, require_user
from app.exceptions import ApiError
from app.repositories.stamp_submission import StampSubmissionRepository
from app.routes.stamp_submission import router
from app.services.stamp_submission import StampSubmissionService, get_stamp_submission_service


def test_liked_and_detail_query_preserve_public_visibility():
    class Session:
        async def execute(self, query):
            sql = str(query.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))
            assert "feed_likes.user_id = 7" in sql
            assert "stamp_submissions.id = 3" in sql
            assert "stamp_submissions.share_to_feed IS true" in sql
            assert "approved" in sql
            return SimpleNamespace(all=lambda: [])
    asyncio.run(StampSubmissionRepository(Session()).list_feed(viewer_user_id=7, liked_only=True, item_id=3))


def test_liked_auth_and_unavailable_detail():
    class Repo:
        async def list_feed(self, **kwargs):
            assert kwargs["item_id"] == 99
            return []
    service = StampSubmissionService(Repo(), None)
    with pytest.raises(ApiError):
        asyncio.run(service.list_feed(liked_only=True))
    with pytest.raises(ApiError):
        asyncio.run(service.feed_detail(99))


def test_detail_and_liked_routes():
    app = FastAPI()
    app.include_router(router)
    @app.exception_handler(ApiError)
    async def api_error(request, exc):
        return JSONResponse(status_code=exc.status, content={"error": exc.code, "message": exc.message})
    class Service:
        async def list_feed(self, **kwargs):
            assert kwargs["liked_only"] and kwargs["user"].id == 7
            return []
        async def feed_detail(self, item_id, actor):
            if item_id == 99:
                raise ApiError(404, "not_found", "Community feed post not found.")
            return {"id": item_id, "is_demo": True, "proof_url": None, "caption": "demo", "author_id": 1,
                    "author_name": "operator", "place_name": None, "sigun": None, "sport_name": None,
                    "approved_at": "2026-09-07T00:00:00", "like_count": 0, "comment_count": 0, "liked_by_me": False}
    app.dependency_overrides[get_stamp_submission_service] = lambda: Service()
    app.dependency_overrides[optional_user] = lambda: None
    client = TestClient(app)
    assert client.get("/api/community-feed/posts/1").json()["isDemo"] is True
    assert client.get("/api/community-feed/posts/0").status_code == 422
    assert client.get("/api/community-feed/posts/99").status_code == 404
    assert client.get("/api/community-feed/liked").status_code == 401
    app.dependency_overrides[require_user] = lambda: LoginUser(7, "test@example.test")
    assert client.get("/api/community-feed/liked").json() == []
