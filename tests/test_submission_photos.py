import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.deps.auth import LoginUser, sign_access_token
from app.exceptions import ApiError
from app.main import app
from app.schemas.stamp_submission import StampSubmissionCreate
from app.services.stamp_submission import StampSubmissionService, get_stamp_submission_service


class Repository:
    saved = None

    async def passport_id(self, _):
        return 1

    async def valid_target(self, *args, **kwargs):
        return True

    async def collected(self, *args):
        return False

    async def pending(self, *args):
        return False

    async def create(self, passport_id, stamp_id, object_key, **kwargs):
        self.saved = SimpleNamespace(id=1, passport_id=passport_id, stamp_id=stamp_id,
            object_key=object_key, status="pending", reviewer_id=None, reviewed_at=None,
            rejection_reason=None, created_at=datetime(2026, 9, 10), updated_at=datetime(2026, 9, 10), **kwargs)
        return self.saved


class Storage:
    def __init__(self):
        self.checked = []
        self.reject = None

    def validate(self, key):
        self.checked.append(key)
        if key == self.reject:
            raise ApiError(400, "bad_request", "Invalid image.")

    def proof_url(self, key):
        return f"https://proof.example/{key}"


def body(**extra):
    return StampSubmissionCreate(stamp_id=2, object_key="proofs/1/2/cover.jpg", **extra)


def test_photos_validate_limits_and_distinct_keys():
    assert body().extra_object_keys == []
    for keys in (["a"] * 5, ["a", "a"], ["proofs/1/2/cover.jpg"], [""], ["a" * 501]):
        with pytest.raises(ValidationError):
            body(extra_object_keys=keys)
    assert len(body(extraObjectKeys=[f"proofs/1/2/{i}.jpg" for i in range(4)]).extra_object_keys) == 4


def test_all_photos_validated_in_order_and_caption_is_opt_in():
    repository, storage = Repository(), Storage()
    service = StampSubmissionService(repository, storage)
    extra = [f"proofs/1/2/{i}.jpg" for i in range(4)]
    response = asyncio.run(service.create(body(extra_object_keys=extra, share_to_feed=True, feed_caption=" 오늘의 도전 "), LoginUser(7, "test@example.com")))
    assert storage.checked == ["proofs/1/2/cover.jpg", *extra]
    assert response["status"] == "pending"
    assert response["proof_urls"] == [storage.proof_url(key) for key in storage.checked]
    assert response["proof_url"] == response["proof_urls"][0]
    assert response["feed_caption"] == "오늘의 도전"
    asyncio.run(service.create(body(feed_caption="비공개 글"), LoginUser(7, "test@example.com")))
    assert repository.saved.feed_caption is None


def test_foreign_or_invalid_extra_photo_prevents_submission():
    repository, storage = Repository(), Storage()
    service = StampSubmissionService(repository, storage)
    with pytest.raises(ApiError):
        asyncio.run(service.create(body(extra_object_keys=["proofs/9/2/other.jpg"]), LoginUser(7, "test@example.com")))
    assert not storage.checked and repository.saved is None
    storage.reject = "proofs/1/2/bad.jpg"
    with pytest.raises(ApiError):
        asyncio.run(service.create(body(extra_object_keys=[storage.reject]), LoginUser(7, "test@example.com")))
    assert repository.saved is None


def test_feed_serializes_gallery_but_not_storage_keys():
    repository, storage = Repository(), Storage()
    service = StampSubmissionService(repository, storage)
    asyncio.run(service.create(body(extra_object_keys=["proofs/1/2/2.jpg"], share_to_feed=True), LoginUser(7, "test@example.com")))
    response = asyncio.run(service._feed_response(repository.saved, None, SimpleNamespace(id=7), engagement_values=(0, 0, False)))
    assert len(response["proof_urls"]) == 2
    assert "object_key" not in response and "extra_object_keys" not in response


def test_gallery_router_success_validation_auth_and_service_failure(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "photo-route-test-secret")
    service = StampSubmissionService(Repository(), Storage())
    app.dependency_overrides[get_stamp_submission_service] = lambda: service
    headers = {"Authorization": f"Bearer {sign_access_token(LoginUser(7, 'test@example.com'))[0]}"}
    payload = {"stamp_id": 2, "object_key": "proofs/1/2/cover.jpg", "extra_object_keys": ["proofs/1/2/2.jpg"]}
    try:
        with TestClient(app) as client:
            assert client.post("/api/stamp-submissions", json=payload).status_code == 401
            response = client.post("/api/stamp-submissions", json=payload, headers=headers)
            assert response.status_code == 201
            assert len(response.json()["proofUrls"]) == 2
            assert client.post("/api/stamp-submissions", json=payload | {"extra_object_keys": ["a"] * 5}, headers=headers).status_code == 400
            invalid = client.post("/api/stamp-submissions", json=payload | {"extra_object_keys": ["proofs/8/2/x.jpg"]}, headers=headers)
            assert invalid.status_code == 400
            assert invalid.json()["error"] == "bad_request"
    finally:
        app.dependency_overrides.pop(get_stamp_submission_service, None)
