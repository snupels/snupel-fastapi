import asyncio
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.deps.auth import LoginUser, sign_access_token
from app.main import app
from app.models import (
    Base, User, Passport, Activity, Stamp, Course, CourseStamp, Badge,
    CollectedBadge, CollectedStamp, StampSubmission, FeedLike, FeedComment,
    SubmissionStatus,
)
from app.repositories.stamp_submission import StampSubmissionRepository
from app.services.stamp_submission import StampSubmissionService, get_stamp_submission_service


def run(value):
    return asyncio.run(value)


@pytest.fixture
def data(monkeypatch):
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    metadata = sa.MetaData()
    for table in Base.metadata.sorted_tables:
        copy = table.to_metadata(metadata)
        for column in copy.c:
            if column.primary_key and isinstance(column.type, sa.BigInteger):
                column.type = sa.Integer()
        if "updated_at" in copy.c:
            copy.c.updated_at.server_default = sa.DefaultClause(sa.text("CURRENT_TIMESTAMP"))
    metadata.create_all(engine)
    with Session(engine) as session:
        class Adapter:
            add = session.add

            async def scalar(self, stmt): return session.scalar(stmt)
            async def scalars(self, stmt): return session.scalars(stmt)
            async def execute(self, stmt): return session.execute(stmt)
            async def flush(self): session.flush()
            async def refresh(self, row): session.refresh(row)
            async def get(self, model, key): return session.get(model, key)

        session.add_all([User(id=1, email="owner@example.com"), User(id=2, email="other@example.com"),
                         User(id=3, email="reviewer@example.com")])
        session.flush()
        session.add(Passport(id=1, user_id=1))
        session.add(Activity(id=1, category="sports", place_name="산악 미션", sport_name="hiking", source="test"))
        session.flush()
        session.add(Stamp(id=1, activity_id=1))
        session.add(Course(id=1, title="테스트 미션", theme="healing", is_published=True, proof_instructions="포토존에서 사진"))
        session.add(Badge(id=1, rule_key="first_mission"))
        session.flush()
        session.add(CourseStamp(course_id=1, stamp_id=1, position=1))
        row = StampSubmission(id=1, passport_id=1, stamp_id=1, object_key="proofs/test.jpg",
            extra_object_keys=["proofs/second.jpg"], feed_caption="보존할 후기", share_to_feed=True,
            status=SubmissionStatus.pending)
        session.add(row)
        session.flush()
        service = StampSubmissionService(StampSubmissionRepository(Adapter()),
                                         SimpleNamespace(proof_url=lambda key: f"https://example.com/{key}"))
        monkeypatch.setenv("JWT_SECRET", "feed-management-test")
        monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
        monkeypatch.setenv("MISSION_REVIEWER_EMAILS", "reviewer@example.com")
        app.dependency_overrides[get_stamp_submission_service] = lambda: service
        try:
            yield session, service, row
        finally:
            app.dependency_overrides.pop(get_stamp_submission_service, None)
    engine.dispose()


def headers(user=1):
    emails = {1: "owner@example.com", 2: "other@example.com", 3: "reviewer@example.com"}
    return {"Authorization": f"Bearer {sign_access_token(LoginUser(user, emails[user]))[0]}"}


def test_operator_approval_private_public_deletion_preserves_awards(data):
    session, service, row = data
    with TestClient(app) as client:
        assert client.get("/api/me/mission-review-permission").status_code == 401
        assert client.get("/api/me/mission-review-permission", headers=headers(1)).json() == {"canReviewMissions": False}
        assert client.get("/api/me/mission-review-permission", headers=headers(3)).json() == {"canReviewMissions": True}
        assert client.get("/api/admin/stamp-submissions", headers=headers(1)).status_code == 403
        pending = client.get("/api/admin/stamp-submissions", headers=headers(3))
        assert pending.status_code == 200, pending.text
        assert pending.headers["cache-control"] == "no-store"
        assert client.get("/api/admin/reward-claims", headers=headers(3)).status_code == 403
        assert pending.json()[0]["courseTitle"] == "테스트 미션"
        assert len(pending.json()[0]["proofUrls"]) == 2
        approve = "/api/admin/stamp-submissions/1/approve"
        assert client.post(approve).status_code == 401
        assert client.post(approve, headers=headers(1)).status_code == 403
        assert client.post(approve, headers=headers(3)).status_code == 200
        assert client.post(approve, headers=headers(3)).status_code == 409
        assert session.scalar(sa.select(sa.func.count()).select_from(CollectedStamp)) == 1
        assert session.scalar(sa.select(sa.func.count()).select_from(CollectedBadge)) == 1
        session.add(FeedLike(submission_id=1, user_id=2))
        session.add(FeedComment(submission_id=1, user_id=2, content="축하해요"))
        session.flush()
        for public in (False, True, False):
            response = client.patch("/api/stamp-submissions/1/feed", headers=headers(), json={"shareToFeed": public})
            assert response.status_code == 200, response.text
            assert response.json()["feedCaption"] == "보존할 후기"
            assert len(client.get("/api/community-feed").json()) == int(public)
            assert len(client.get("/api/community-feed/me", headers=headers()).json()) == 1
            assert client.get("/api/community-feed/posts/1", headers=headers()).status_code == 200
            assert client.get("/api/community-feed/posts/1", headers=headers(2)).status_code == (200 if public else 404)
            assert len(client.get("/api/community-feed/users/1", headers=headers(2)).json()) == int(public)
            assert len(client.get("/api/community-feed/liked", headers=headers(2)).json()) == int(public)
            assert client.get("/api/community-feed/1/comments").status_code == (200 if public else 404)
            assert client.post("/api/community-feed/1/like", headers=headers(2)).status_code == (200 if public else 404)
        for _ in range(2):
            assert client.delete("/api/stamp-submissions/1/feed", headers=headers()).status_code == 204
        assert client.get("/api/community-feed/me", headers=headers()).json() == []
        assert client.get("/api/community-feed/posts/1", headers=headers()).status_code == 404
        assert client.patch("/api/stamp-submissions/1/feed", headers=headers(), json={"shareToFeed": True}).status_code == 404
        assert row.status == SubmissionStatus.approved and row.feed_deleted_at is not None
        assert row.feed_caption == "보존할 후기" and len(row.extra_object_keys) == 1
        assert session.scalar(sa.select(sa.func.count()).select_from(CollectedStamp)) == 1
        assert session.scalar(sa.select(sa.func.count()).select_from(CollectedBadge)) == 1
        assert len(run(service.repository.completed_mission_facts(1))) == 1


def test_feed_owner_authorization_validation_and_rejection(data):
    _, _, row = data
    with TestClient(app) as client:
        path = "/api/stamp-submissions/1/feed"
        assert client.delete(path).status_code == 401
        assert client.patch(path, json={"shareToFeed": True}).status_code == 401
        assert client.delete(path, headers=headers(2)).status_code == 404
        assert client.patch(path, headers=headers(2), json={"shareToFeed": True}).status_code == 404
        assert client.patch(path, headers=headers(), json={}).status_code == 400
        assert client.delete("/api/stamp-submissions/0/feed", headers=headers()).status_code == 400
        assert client.delete("/api/stamp-submissions/999/feed", headers=headers()).status_code == 404
        reject = "/api/admin/stamp-submissions/1/reject"
        assert client.post(reject, headers=headers(3), json={"reason": " "}).status_code == 400
        assert client.post(reject, headers=headers(1), json={"reason": "불일치"}).status_code == 403
        assert client.post(reject, headers=headers(3), json={"reason": "장소 표지가 보이지 않습니다"}).status_code == 200
        assert row.status == SubmissionStatus.rejected
        assert client.get("/api/community-feed/me", headers=headers()).json() == []
