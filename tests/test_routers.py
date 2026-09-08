import asyncio
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import mysql

from app.deps.auth import LoginUser, sign_access_token
from app.exceptions import ApiError
from app.main import app
from app.repositories.activity import ActivityRepository
from app.models import StampCatalog
from app.services.activity import get_activity_service
from app.services.badge import get_badge_service
from app.services.collected_badge import get_collected_badge_service
from app.services.collected_stamp import get_collected_stamp_service
from app.services.course import get_course_service
from app.services.passport import get_passport_service
from app.services.recommendation import get_recommendation_service
from app.services.stamp_catalog import get_stamp_catalog_service
from app.services.stamp_submission import get_stamp_submission_service

NOW = datetime(2026, 1, 1).isoformat()


class FakeService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    async def create(self, _body, _actor):
        if self.error:
            raise self.error
        return self.result

    async def list(self, _actor=None, *, offset, limit):
        self.pagination = (offset, limit)
        return self.result

    async def map_items(self, **filters):
        self.map_filters = filters
        return self.result


CASES = [
    (
        "/api/badges",
        get_badge_service,
        True,
        {"description": "badge"},
        {"id": 1, "image_url": None, "description": "badge", "created_at": NOW, "updated_at": NOW},
    ),
    (
        "/api/activities",
        get_activity_service,
        True,
        {"category": "sports", "sport_name": "hiking"},
        {"id": 1, "category": "sports", "representative_image_url": None, "sport_name": "hiking", "region": None, "place_name": None, "latitude": None, "longitude": None, "created_at": NOW, "updated_at": NOW},
    ),
    (
        "/api/courses",
        get_course_service,
        True,
        {"theme": "healing"},
        {"id": 1, "category": "tour", "sport_name": None, "recommended_companion": None, "representative_image_url": None, "estimated_duration_minutes": None, "theme": "healing", "created_at": NOW, "updated_at": NOW},
    ),
    (
        "/api/passports",
        get_passport_service,
        True,
        {"user_id": 7},
        {"id": 1, "user_id": 7, "created_at": NOW, "updated_at": NOW},
    ),
    (
        "/api/collected-badges",
        get_collected_badge_service,
        True,
        {"passport_id": 1, "badge_id": 2},
        {"id": 1, "passport_id": 1, "badge_id": 2, "collected_at": NOW},
    ),
    (
        "/api/collected-stamps",
        get_collected_stamp_service,
        True,
        {"passport_id": 1, "stamp_id": 2},
        {"id": 1, "passport_id": 1, "stamp_id": 2, "collected_at": NOW},
    ),
]


def token(email: str) -> str:
    return sign_access_token(LoginUser(7, email))[0]


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "router-test-secret")
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.mark.parametrize("path,dependency,admin,body,result", CASES)
def test_router_success_validation_auth_and_service_errors(path, dependency, admin, body, result):
    headers = {"Authorization": f"Bearer {token('admin@example.com' if admin else 'user@example.com')}"}
    app.dependency_overrides[dependency] = lambda: FakeService(result=result)

    with TestClient(app) as client:
        success = client.post(path, json=body, headers=headers)
        assert success.status_code == 201

        invalid = client.post(path, json={}, headers=headers)
        assert invalid.status_code == 400
        assert invalid.json() == {"error": "bad_request", "message": "Invalid request body."}

        assert client.post(path, json=body).status_code == 401
        if admin:
            user_headers = {"Authorization": f"Bearer {token('user@example.com')}"}
            assert client.post(path, json=body, headers=user_headers).status_code == 403

        app.dependency_overrides[dependency] = lambda: FakeService(
            error=ApiError(409, "conflict", "Already exists.")
        )
        conflict = client.post(path, json=body, headers=headers)
        assert conflict.status_code == 409
        assert conflict.json() == {"error": "conflict", "message": "Already exists."}


def test_health_and_openapi():
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.get("/api/docs").status_code == 200
        activity_category = client.get("/api/docs").json()["components"]["schemas"][
            "ActivityCategory"
        ]

    assert activity_category["enum"] == ["tour", "sports", "event"]


def test_course_recommendations_are_available_to_logged_in_users():
    class RecommendationService:
        async def recommend(self, _body, *, user_id):
            assert user_id == 7
            return {
                "title": "강원특별자치도 힐링 추천 코스",
                "description": "힐링 테마에 맞춘 장소와 이동 동선을 고려한 일정입니다.",
                "activity_minutes": 0,
                "travel_minutes": 0,
                "total_estimated_minutes": 0,
                "stops": [],
                "legs": [],
                "used_ai": False,
                "match_score": 0,
            }

    app.dependency_overrides[get_recommendation_service] = RecommendationService
    headers = {"Authorization": f"Bearer {token('user@example.com')}"}
    body = {"theme": "healing", "region": "강원특별자치도", "availableMinutes": 120}

    with TestClient(app) as client:
        assert client.post("/api/course-recommendations", json=body).status_code == 401
        response = client.post("/api/course-recommendations", json=body, headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "title": "강원특별자치도 힐링 추천 코스",
        "description": "힐링 테마에 맞춘 장소와 이동 동선을 고려한 일정입니다.",
        "activityMinutes": 0,
        "travelMinutes": 0,
        "totalEstimatedMinutes": 0,
        "stops": [],
        "legs": [],
        "usedAi": False,
        "matchScore": 0,
    }


def test_only_admin_can_generate_ai_mission_drafts():
    class RecommendationService:
        async def generate_mission(self, body):
            assert body.title == "설악산 힐링 미션"
            return {
                "course": {
                    "id": 9,
                    "category": "sports",
                    "sport_name": "hiking",
                    "recommended_companion": None,
                    "representative_image_url": None,
                    "estimated_duration_minutes": 90,
                    "theme": "healing",
                    "title": body.title,
                    "description": None,
                    "is_published": False,
                    "created_at": NOW,
                    "updated_at": NOW,
                },
                "title": "설악산 힐링 코스",
                "description": "등산과 휴식을 잇는 코스입니다.",
                "activity_minutes": 90,
                "travel_minutes": 0,
                "total_estimated_minutes": 90,
                "stops": [{
                    "activity_id": 4,
                    "place_name": "설악산",
                    "address": None,
                    "latitude": 38.1,
                    "longitude": 128.4,
                    "representative_image_url": None,
                    "reason": "fit",
                    "estimated_minutes": 90,
                }],
                "legs": [],
                "used_ai": True,
                "match_score": 96,
            }

    app.dependency_overrides[get_recommendation_service] = RecommendationService
    body = {
        "title": "설악산 힐링 미션",
        "theme": "healing",
        "region": "강원특별자치도",
        "sport": "hiking",
        "availableMinutes": 120,
    }
    user_headers = {"Authorization": f"Bearer {token('user@example.com')}"}
    admin_headers = {"Authorization": f"Bearer {token('admin@example.com')}"}

    with TestClient(app) as client:
        assert client.post(
            "/api/admin/course-missions/generate", json=body, headers=user_headers
        ).status_code == 403
        response = client.post(
            "/api/admin/course-missions/generate", json=body, headers=admin_headers
        )

    assert response.status_code == 201
    assert response.json()["course"]["isPublished"] is False
    assert response.json()["matchScore"] == 96


def test_stamp_catalog_is_public_and_serves_images():
    service = FakeService(result=[
        {"id": 1, "region_ko": "춘천", "region_en": "CHUNCHEON", "sport_ko": "산악", "sport_en": "MOUNTAIN", "color": "#2F6B4F", "image_url": "https://assets.example.com/stamps/01-chuncheon-mountain.svg", "created_at": NOW, "updated_at": NOW}
    ])
    app.dependency_overrides[get_stamp_catalog_service] = lambda: service

    with TestClient(app) as client:
        response = client.get("/api/stamp-catalog")
        assert response.status_code == 200
        assert response.json()[0]["imageUrl"].endswith("01-chuncheon-mountain.svg")


def test_stamp_catalog_builds_public_s3_url(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "sportspassport-asset")
    monkeypatch.delenv("STAMP_IMAGE_BASE_URL", raising=False)
    stamp = StampCatalog(image_key="stamps/01-chuncheon-mountain.svg")
    assert stamp.image_url == (
        "https://sportspassport-asset.s3.ap-northeast-2.amazonaws.com/"
        "stamps/01-chuncheon-mountain.svg"
    )


def test_cors_allows_sportspassport_kr():
    with TestClient(app) as client:
        response = client.options(
            "/api/health",
            headers={
                "Origin": "https://sportspassport.kr",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://sportspassport.kr"


def test_list_pagination_defaults_limits_and_openapi():
    service = FakeService(result=[])
    app.dependency_overrides[get_badge_service] = lambda: service

    with TestClient(app) as client:
        assert client.get("/api/badges").json() == []
        assert service.pagination == (0, 20)
        assert client.get("/api/badges?page=3&size=10").status_code == 200
        assert service.pagination == (20, 10)
        assert client.get("/api/badges?size=101").status_code == 400

        for operations in client.get("/api/docs").json()["paths"].values():
            operation = operations.get("get")
            if not operation:
                continue
            schema = operation["responses"].get("200", {}).get("content", {}).get(
                "application/json", {}
            ).get("schema", {})
            if schema.get("type") != "array":
                continue
            parameters = {item["name"]: item["schema"] for item in operation["parameters"]}
            if "page" not in parameters:
                continue
            assert parameters["page"]["default"] == 1
            assert parameters["size"]["default"] == 20
            assert parameters["size"]["maximum"] == 100


def test_activity_map_returns_viewport_markers_only():
    service = FakeService(result=[
        {
            "id": 1,
            "category": "sports",
            "place_name": "서울광장",
            "sport_name": "running",
            "latitude": 37.5665,
            "longitude": 126.9780,
            "has_mission": True,
        }
    ])
    app.dependency_overrides[get_activity_service] = lambda: service

    with TestClient(app) as client:
        response = client.get(
            "/api/activities/map?south=37.5&west=126.9&north=37.6&east=127.0&category=sports"
        )

    assert response.status_code == 200
    assert response.json() == [{
        "id": 1,
        "category": "sports",
        "placeName": "서울광장",
        "sportName": "running",
        "latitude": 37.5665,
        "longitude": 126.978,
        "hasMission": True,
    }]
    assert service.map_filters == {
        "south": 37.5,
        "west": 126.9,
        "north": 37.6,
        "east": 127.0,
        "category": "sports",
        "sport": None,
        "mission": None,
        "limit": 300,
    }


def test_activity_map_rejects_inverted_bounds():
    with TestClient(app) as client:
        response = client.get("/api/activities/map?south=37.6&west=126.9&north=37.5&east=127.0")

    assert response.status_code == 400
    assert response.json() == {"error": "bad_request", "message": "Invalid map bounds."}


@pytest.mark.parametrize(
    ("path", "dependency"),
    [
        ("/api/badges", get_badge_service),
        ("/api/activities", get_activity_service),
        ("/api/courses", get_course_service),
    ],
)
def test_data_lists_are_public(path, dependency):
    app.dependency_overrides[dependency] = lambda: FakeService(result=[])
    with TestClient(app) as client:
        assert client.get(path).status_code == 200


@pytest.mark.parametrize(
    ("path", "dependency"),
    [
        ("/api/passports", get_passport_service),
        ("/api/collected-badges", get_collected_badge_service),
        ("/api/collected-stamps", get_collected_stamp_service),
    ],
)
def test_personal_data_lists_are_admin_only(path, dependency):
    app.dependency_overrides[dependency] = lambda: FakeService(result=[])
    user_headers = {"Authorization": f"Bearer {token('user@example.com')}"}
    admin_headers = {"Authorization": f"Bearer {token('admin@example.com')}"}
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
        assert client.get(path, headers=user_headers).status_code == 403
        assert client.get(path, headers=admin_headers).status_code == 200


def test_stamp_submission_routes_are_private_and_admin_review_has_activity():
    submission = {
        "id": 1,
        "passport_id": 4,
        "stamp_id": 2,
        "object_key": "proofs/4/2/x.jpg",
        "status": "pending",
        "reviewer_id": None,
        "reviewed_at": None,
        "rejection_reason": None,
        "proof_url": "https://signed.example.com/proof",
        "created_at": NOW,
        "updated_at": NOW,
    }

    class Service:
        async def upload_url(self, _body, actor):
            assert actor.id == 7
            return {
                "upload_url": "https://upload.example.com",
                "fields": {"key": "proofs/4/2/x.jpg"},
                "object_key": "proofs/4/2/x.jpg",
                "expires_in": 600,
            }

        async def create(self, _body, actor):
            assert actor.id == 7
            return submission

        async def list_user(self, actor, *, offset, limit):
            assert actor.id == 7
            assert (offset, limit) == (0, 20)
            return [submission]

        async def list_feed(self, *, user=None, owner_user_id=None, offset, limit):
            if user is not None:
                assert user.id == 7
            if owner_user_id is not None:
                assert owner_user_id == 7
            assert (offset, limit) == (0, 20)
            return [
                {
                    "id": 1,
                    "proof_url": "https://signed.example.com/proof",
                    "caption": "설악산 완주!",
                    "author_id": 7,
                    "author_name": "강원 스포츠 탐험가",
                    "place_name": "설악산 트레일 챌린지",
                    "sigun": "속초시",
                    "sport_name": "트레킹",
                    "approved_at": NOW,
                }
            ]

        async def update_feed_visibility(self, item_id, body, actor):
            assert (item_id, actor.id) == (1, 7)
            assert body.share_to_feed is True
            return submission | {
                "share_to_feed": True,
                "feed_caption": body.feed_caption,
            }

        async def list_admin(self, status, *, offset, limit):
            assert status.value == "pending"
            assert (offset, limit) == (0, 20)
            return [
                submission
                | {
                    "activity": {
                        "id": 9,
                        "category": "event",
                        "place_name": "강릉 스포츠 행사",
                        "address": "강릉시",
                        "starts_at": NOW,
                        "ends_at": NOW,
                    }
                }
            ]

    app.dependency_overrides[get_stamp_submission_service] = Service
    user_headers = {"Authorization": f"Bearer {token('user@example.com')}"}
    admin_headers = {"Authorization": f"Bearer {token('admin@example.com')}"}

    with TestClient(app) as client:
        assert client.get("/api/stamp-submissions").status_code == 401
        assert client.get("/api/stamp-submissions", headers=user_headers).status_code == 200
        assert client.get("/api/admin/stamp-submissions", headers=user_headers).status_code == 403
        admin = client.get("/api/admin/stamp-submissions", headers=admin_headers)
        upload = client.post(
            "/api/stamp-submissions/upload-url",
            json={"passportId": 4, "stampId": 2, "contentType": "image/jpeg"},
            headers=user_headers,
        )
        created = client.post(
            "/api/stamp-submissions",
            json={
                "passportId": 4,
                "stampId": 2,
                "objectKey": "proofs/4/2/x.jpg",
            },
            headers=user_headers,
        )
        public_feed = client.get("/api/community-feed")
        assert client.get("/api/community-feed/me").status_code == 401
        own_feed = client.get("/api/community-feed/me", headers=user_headers)
        visibility = client.patch(
            "/api/stamp-submissions/1/feed",
            json={"shareToFeed": True, "feedCaption": "  설악산 완주!  "},
            headers=user_headers,
        )

    assert admin.status_code == 200
    assert admin.json()[0]["activity"] == {
        "id": 9,
        "category": "event",
        "placeName": "강릉 스포츠 행사",
        "sportName": None,
        "sigun": None,
        "representativeImageUrl": None,
        "address": "강릉시",
        "startsAt": NOW,
        "endsAt": NOW,
    }
    assert upload.status_code == 200
    assert created.status_code == 201
    assert public_feed.status_code == 200
    assert public_feed.json()[0]["authorName"] == "강원 스포츠 탐험가"
    assert own_feed.status_code == 200
    assert visibility.status_code == 200
    assert visibility.json()["feedCaption"] == "설악산 완주!"


def test_stamp_submission_reject_requires_non_blank_reason():
    app.dependency_overrides[get_stamp_submission_service] = lambda: object()
    headers = {"Authorization": f"Bearer {token('admin@example.com')}"}
    with TestClient(app) as client:
        response = client.post(
            "/api/admin/stamp-submissions/1/reject",
            json={"reason": "   "},
            headers=headers,
        )
    assert response.status_code == 400
    assert response.json() == {"error": "bad_request", "message": "Invalid request body."}


def test_activity_pagination_compiles_for_mysql_with_mission_filters():
    statements = []

    class Result:
        def all(self):
            return []

        def mappings(self):
            return self

    class Session:
        async def execute(self, statement):
            statements.append(statement)
            return Result()

    repository = ActivityRepository(Session())
    for mission in (True, False):
        asyncio.run(
            repository.explore(
                region=None,
                sigun="강릉시",
                sport=None,
                theme=None,
                mission=mission,
                offset=20,
                limit=20,
            )
        )
    asyncio.run(
        repository.map_items(
            south=37.5,
            west=126.9,
            north=37.6,
            east=127.0,
            category=None,
            sport=None,
            mission=None,
            limit=300,
        )
    )

    sql = [
        str(statement.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))
        for statement in statements
    ]
    assert all("LIMIT 20, 20" in statement for statement in sql[:2])
    assert all("LIMIT 20, 20" in statement for statement in sql[:2])
    assert all("activities.sigun = '강릉시'" in statement for statement in sql[:2])
    assert "EXISTS" in sql[0] and "NOT (EXISTS" in sql[1]
    assert all(
        "coalesce(activities.last_synced_at, activities.created_at) DESC" in statement
        for statement in sql[:2]
    )
    assert "IS NOT NULL" in sql[2]
    assert "BETWEEN 37.5 AND 37.6" in sql[2]


def test_activity_explore_forwards_sigun_filter():
    service = FakeService(result=[])

    async def explore(**filters):
        service.filters = filters
        return []

    service.explore = explore
    app.dependency_overrides[get_activity_service] = lambda: service

    with TestClient(app) as client:
        assert client.get("/api/sports?q= 스키 &sigun=강릉시").status_code == 200

    assert service.filters["sigun"] == "강릉시"
    assert service.filters["q"] == " 스키 "


def test_course_itinerary_returns_ordered_stops():
    class Service:
        async def itinerary(self, item_id):
            assert item_id == 7
            return {
                "id": 7,
                "title": "강릉 스포츠 코스",
                "description": None,
                "category": "sports",
                "sport_name": "running",
                "theme": "thrill",
                "recommended_companion": "friends",
                "estimated_duration_minutes": 45,
                "stops": [
                    {
                        "position": 1,
                        "stamp_id": 2,
                        "activity_id": 3,
                        "category": "sports",
                        "place_name": "강릉 종합운동장",
                        "sport_name": "running",
                        "address": "강릉시",
                        "latitude": 37.7,
                        "longitude": 128.8,
                        "estimated_minutes": 45,
                    }
                ],
            }

    app.dependency_overrides[get_course_service] = Service
    with TestClient(app) as client:
        response = client.get("/api/courses/7/itinerary")

    assert response.status_code == 200
    assert response.json()["stops"][0] == {
        "position": 1,
        "stampId": 2,
        "activityId": 3,
        "category": "sports",
        "placeName": "강릉 종합운동장",
        "sportName": "running",
        "address": "강릉시",
        "latitude": 37.7,
        "longitude": 128.8,
        "estimatedMinutes": 45,
    }
