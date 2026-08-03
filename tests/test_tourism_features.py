import asyncio
import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.deps.auth import LoginUser
from app.exceptions import ApiError
from app.jobs.sync_tourism import (
    TourismSync,
    durunubi_item,
    in_gangwon,
    items,
    mountain_item,
    tourism_item,
)
from app.models import ActivityCategory, CollectedStamp, CourseTheme, SubmissionStatus
from app.repositories.stamp_submission import StampSubmissionRepository
from app.schemas.recommendation import CourseRecommendationRequest
from app.schemas.activity import ActivityCreate, ActivityPatch
from app.schemas.stamp_submission import StampSubmissionCreate
from app.services.activity import ActivityService
from app.services.recommendation import RecommendationService
from app.services.stamp_submission import StampSubmissionService
from app.services.weather import WeatherService, base_datetime, grid, weather_cache


def test_tourism_pagination_and_normalization():
    class Sync(TourismSync):
        async def _get(self, _url, params):
            batch = [{"id": 1}, {"id": 2}] if params["pageNo"] == 1 else [{"id": 3}]
            return {"response": {"body": {"items": {"item": batch}, "totalCount": 3}}}

    sync = Sync(None, None, "key")
    assert asyncio.run(sync._pages("url", {})) == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert items({"response": {"body": {"items": {"item": {"id": 1}}, "totalCount": 1}}}) == ([{"id": 1}], 1)
    assert items({"response": {"body": {"items": "", "totalCount": 0}}}) == ([], 0)

    place = {"contentid": "6", "title": "경포대", "addr1": "강원특별자치도 강릉시 경포로 365"}
    trail = {
        "routeIdx": "7",
        "crsKorNm": "해파랑길",
        "crsLat": "37.5",
        "crsLon": "128.2",
        "sigun": "강릉시",
    }
    mountain = {"mtnId": "8", "mtnNm": "설악산", "addrNm": "강원특별자치도 속초시"}
    assert in_gangwon(trail)
    assert tourism_item(place)["sigun"] == "강릉시"
    assert durunubi_item(trail)["sigun"] == "강릉시"
    assert mountain_item(mountain)["sigun"] == "속초시"
    assert durunubi_item(trail)["external_id"] == "7"
    assert mountain_item(mountain)["place_name"] == "설악산"


def test_activity_categories_require_sport_type_only_for_sports():
    assert ActivityCreate(category="tour").category == ActivityCategory.tour
    assert ActivityCreate(category="event").category == ActivityCategory.event
    assert ActivityCreate(category="sports", sport_name="hiking").sport_name == "hiking"
    with pytest.raises(ValueError):
        ActivityCreate(category="sports")
    with pytest.raises(ValueError):
        ActivityCreate(category="tour", sport_name="hiking")


def test_activity_category_update_cannot_keep_sport_type_on_non_sports():
    class Repository:
        async def get(self, _):
            return SimpleNamespace(category=ActivityCategory.sports, sport_name="hiking")

    with pytest.raises(ApiError):
        asyncio.run(ActivityService(Repository(), "Activity").update(1, ActivityPatch(category="event")))


def test_tourism_sync_requests_durunubi_json():
    calls = []

    class Sync(TourismSync):
        async def _pages(self, url, params):
            calls.append((url, params))
            return [{"code": "32", "name": "강원"}] if url.endswith("/areaCode2") else []

    class Repository:
        async def sync_source(self, *_):
            return 0

    asyncio.run(Sync(None, Repository(), "key").run())
    assert next(params for url, params in calls if "Durunubi" in url)["_type"] == "json"


def test_weather_grid_base_time_and_cache(monkeypatch):
    assert grid(37.5665, 126.9780) == (60, 127)
    assert base_datetime(datetime(2026, 7, 21, 1, 30)) == datetime(2026, 7, 20, 23)

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "response": {
                    "body": {
                        "items": {
                            "item": [
                                {"fcstDate": "20260721", "fcstTime": "1200", "category": "TMP", "fcstValue": "24"},
                                {"fcstDate": "20260721", "fcstTime": "1200", "category": "POP", "fcstValue": "30"},
                                {"fcstDate": "20260721", "fcstTime": "1200", "category": "SKY", "fcstValue": "3"},
                                {"fcstDate": "20260721", "fcstTime": "1200", "category": "PTY", "fcstValue": "0"},
                            ]
                        }
                    }
                }
            }

    class Client:
        calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def get(self, *_args, **_kwargs):
            Client.calls += 1
            return Response()

    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "key")
    monkeypatch.setattr("app.services.weather.httpx.AsyncClient", lambda **_: Client())
    weather_cache.clear()
    service = WeatherService()
    now = datetime(2026, 7, 21, 11, 30)
    first = asyncio.run(service.forecast(37.5665, 126.9780, now))
    second = asyncio.run(service.forecast(37.5665, 126.9780, now))
    assert first == second
    assert first["temperature_c"] == 24
    assert Client.calls == 1


def test_recommendation_uses_only_safe_candidates_and_validates_ai(monkeypatch, caplog):
    candidate = SimpleNamespace(
        id=4,
        place_name="설악산",
        category=ActivityCategory.sports,
        region="강원특별자치도",
        sport_name="hiking",
        source_metadata={"duration_minutes": 90},
        latitude=38.1,
        longitude=128.4,
    )

    class Repository:
        async def recommendation_candidates(self, *_):
            return [candidate]

    class Weather:
        async def forecast(self, *_):
            return {"sky": "clear"}

    captured = {}

    class Response:
        invalid = False

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {"message": {"content": json.dumps({"stops": [{"activityId": 999 if self.invalid else 4, "reason": "fit", "estimatedMinutes": 90}]})}}
                ]
            }

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def post(self, _url, **kwargs):
            captured.update(kwargs["json"])
            return Response()

    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    monkeypatch.setattr("app.services.recommendation.httpx.AsyncClient", lambda **_: Client())
    body = CourseRecommendationRequest(
        theme=CourseTheme.healing,
        region="강원특별자치도",
        sport="hiking",
        availableMinutes=120,
    )
    result = asyncio.run(RecommendationService(Repository(), Weather()).recommend(body))
    prompt = captured["messages"][1]["content"]
    assert result == {
        "stops": [{"activity_id": 4, "reason": "fit", "estimated_minutes": 90}],
        "used_ai": True,
    }
    assert "latitude" not in prompt and "longitude" not in prompt and "email" not in prompt
    assert captured["provider"]["data_collection"] == "deny"
    Response.invalid = True
    fallback = asyncio.run(RecommendationService(Repository(), Weather()).recommend(body))
    assert fallback["used_ai"] is False
    assert fallback["stops"][0]["activity_id"] == 4
    assert "OpenRouter recommendation fallback" in caplog.text


def test_stamp_submission_requires_owned_published_mission_and_prefix():
    class Repository:
        async def valid_target(self, *_):
            return True

        async def collected(self, *_):
            return False

        async def pending(self, *_):
            return False

        async def create(self, passport_id, stamp_id, object_key):
            return SimpleNamespace(
                id=1,
                passport_id=passport_id,
                stamp_id=stamp_id,
                object_key=object_key,
                status=SubmissionStatus.pending,
                reviewer_id=None,
                reviewed_at=None,
                rejection_reason=None,
                created_at=datetime(2026, 1, 1),
                updated_at=datetime(2026, 1, 1),
            )

    class Storage:
        def proof_url(self, _):
            return "signed"

    service = StampSubmissionService(Repository(), Storage())
    user = LoginUser(7, "user@example.com")
    invalid = StampSubmissionCreate(passport_id=1, stamp_id=2, object_key="proofs/9/2/x.jpg")
    with pytest.raises(ApiError) as error:
        asyncio.run(service.create(invalid, user))
    assert error.value.status == 400

    valid = StampSubmissionCreate(passport_id=1, stamp_id=2, object_key="proofs/1/2/x.jpg")
    result = asyncio.run(service.create(valid, user))
    assert result["status"] == SubmissionStatus.pending
    assert result["proof_url"] == "signed"


def test_approving_submission_creates_collected_stamp():
    class Session:
        added = []

        def add(self, row):
            self.added.append(row)

        async def flush(self):
            pass

        async def refresh(self, _row):
            pass

    session = Session()
    repository = StampSubmissionRepository(session)

    async def not_collected(*_):
        return False

    repository.collected = not_collected
    row = SimpleNamespace(
        passport_id=1,
        stamp_id=2,
        status=SubmissionStatus.pending,
        reviewer_id=None,
        reviewed_at=None,
        rejection_reason=None,
    )
    asyncio.run(repository.approve(row, 7))
    assert isinstance(session.added[0], CollectedStamp)
    assert row.status == SubmissionStatus.approved
    assert row.reviewer_id == 7
