import asyncio
import json
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import mysql

from app.deps.auth import LoginUser
from app.exceptions import ApiError
from app.main import app
from app.models import ActivityCategory
from app.repositories.activity import ActivityRepository
from app.routes.recommendation import rate_limiter
from app.schemas.recommendation import CourseRecommendationRequest, CourseRecommendationResponse
from app.services.course_schedule import opening_windows, role, schedule
from app.services.recommendation import HOURS_CACHE, RecommendationService, get_recommendation_service


def place(item_id, kind="activity", **values):
    metadata = {"duration_minutes": 120 if kind == "activity" else 60 if kind == "meal" else 30}
    if kind in {"meal", "rest"}:
        metadata["contenttypeid"] = "39"
    return SimpleNamespace(**(dict(
        id=item_id, place_name=f"카페 {item_id}" if kind == "rest" else f"장소 {item_id}",
        category=ActivityCategory.sports if kind == "activity" else ActivityCategory.tour,
        sport_name="surfing" if kind == "activity" else None,
        region="강원특별자치도", sigun="양양군", latitude=37.97 + item_id * .001,
        longitude=128.76, summary=None, address="강원특별자치도 양양군 현남면",
        source_metadata=metadata, representative_image_url=None, source=None, external_id=None,
        starts_at=None, ends_at=None,
    ) | values))


def body(**values):
    return CourseRecommendationRequest(**(dict(theme="healing", region="강원특별자치도",
                                              sigun="양양군", sport="marine", availableMinutes=360,
                                              travelDate="2026-10-20", startTime="09:00") | values))


def test_one_experience_connects_meal_sightseeing_and_rest_without_inventing_hours(monkeypatch):
    candidates = [place(1), place(2), place(3), place(4, "meal"), place(5, "sightseeing"), place(6, "rest")]

    class Repository:
        async def recommendation_candidates(self, *_args, **_kwargs):
            return candidates

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    request = body()
    result = asyncio.run(RecommendationService(Repository(), None).recommend(request))
    assert result["used_ai"] is False
    assert {stop["role"] for stop in result["stops"]} == {"activity", "meal", "sightseeing", "rest"}
    assert sum(stop["role"] == "activity" for stop in result["stops"]) == 1
    assert result["total_estimated_minutes"] <= request.available_minutes
    assert result["total_estimated_minutes"] == result["activity_minutes"] + result["travel_minutes"] + result["waiting_minutes"]
    assert all(stop["hours_status"] == "unknown" for stop in result["stops"])
    assert all(stop["opening_hours"] is None for stop in result["stops"])
    assert all("미확인" not in stop["reason"] for stop in result["stops"])
    assert result["planning_notes"]
    assert CourseRecommendationResponse.model_validate(result)


def test_multiple_surf_schools_are_not_returned_as_a_tour():
    service = RecommendationService(None, None)
    candidates = [place(1), place(2), place(3)]
    stops = service._fallback(candidates, body())
    assert len(stops) == 1
    with pytest.raises(ValueError, match="repeats the main experience"):
        service._ai_stops([{"activityId": 1, "reason": "서핑"}, {"activityId": 2, "reason": "서핑"}], candidates, body())
    result = service._result(stops, candidates, body(), used_ai=False)
    assert "포함되지" in result["planning_notes"][0]


def test_weekday_closure_and_event_dates_cannot_enter_an_itinerary():
    service = RecommendationService(None, None)
    monday = body(travelDate="2026-10-19")
    candidates = [place(1, source_metadata={"hours": "09:00~18:00", "closed": "매주 월요일 휴무"})]
    assert service._fallback(candidates, monday) == []
    assert service._fallback(candidates, body(travelDate="2026-10-20"))
    candidates[0].starts_at = datetime(2026, 10, 21)
    assert service._fallback(candidates, body(travelDate="2026-10-20")) == []
    candidates[0].starts_at = None
    candidates[0].ends_at = datetime(2026, 10, 19)
    assert service._fallback(candidates, body(travelDate="2026-10-20")) == []


def test_opening_wait_is_counted_and_stay_finishes_before_closing():
    service = RecommendationService(None, None)
    activity = place(1, source_metadata={"duration_minutes": 120, "hours": "10:00~12:00"})
    request = body(availableMinutes=180)
    stops = service._fallback([activity], request)
    result = service._result(stops, [activity], request, used_ai=False)
    assert result["stops"][0]["arrival_time"] == "10:00"
    assert result["stops"][0]["departure_time"] == "12:00"
    assert result["waiting_minutes"] == 60
    assert result["total_estimated_minutes"] == 180
    assert result["stops"][0]["hours_status"] == "provided"
    assert service._fallback([activity], body(availableMinutes=179)) == []


def test_morning_sightseeing_can_precede_a_later_opening_main_activity():
    service = RecommendationService(None, None)
    activity = place(1, source_metadata={"duration_minutes": 90, "hours": "11:00~17:00"})
    view = place(2, "sightseeing", source_metadata={"duration_minutes": 60})
    stops = service._fallback([activity, view], body())
    assert [stop["activity_id"] for stop in stops] == [2, 1]


def test_breaks_are_not_treated_as_open_and_ambiguous_text_remains_unknown():
    day = date(2026, 10, 20)
    candidate = place(1, source_metadata={"hours": "09:00~18:00 (브레이크타임 12:00~13:00)"})
    assert opening_windows(candidate, day)[0] == [(540, 720), (780, 1080)]
    service = RecommendationService(None, None)
    assert schedule([candidate], body(startTime="11:00", availableMinutes=180),
                    service._minutes, service._travel_minutes, main_id=1) is None
    for raw in ("평일 09:00~18:00 주말 10:00~17:00", "3월~10월 09:00~18:00", "연중무휴", "운영시간 문의"):
        candidate.source_metadata = {"hours": raw}
        assert opening_windows(candidate, day)[0] is None
    candidate.source_metadata = {"hours": "24시간"}
    assert opening_windows(candidate, day)[0] == [(0, 1440)]


def test_lunch_is_scheduled_near_midday_not_immediately_at_9am():
    service = RecommendationService(None, None)
    meal = place(1, "meal")
    assert schedule([meal], body(), service._minutes, service._travel_minutes, main_id=999) is None
    timing = schedule([meal], body(startTime="10:30"), service._minutes, service._travel_minutes, main_id=999)
    assert timing[0]["arrival_time"] == "11:00"
    assert timing[0]["waiting_minutes"] == 30


def test_candidate_sampling_keeps_support_roles_amid_many_surfing_businesses():
    service = RecommendationService(None, None)
    candidates = [place(i) for i in range(1, 35)] + [place(40, "meal"), place(41, "rest"), place(42, "sightseeing")]
    pool = service._coherent_candidates(candidates, body())
    assert len(pool) <= 10
    assert {role(item) for item in pool} >= {"activity", "meal", "rest", "sightseeing"}


def test_database_reserves_food_and_tourism_capacity_without_losing_sport_or_history_filters():
    statements = []
    class Session:
        async def execute(self, statement):
            statements.append(str(statement.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True})))
            return SimpleNamespace(all=lambda: [])
    asyncio.run(ActivityRepository(Session()).recommendation_candidates(
        "강원특별자치도", "양양군", "marine", "healing", user_id=7,
    ))
    assert len(statements) == 3
    assert "'39'" in statements[1] and "json_extract" in statements[1]
    assert "'12', '14'" in statements[2]
    assert all("양양군" in sql and "passports.user_id = 7" in sql for sql in statements)


def test_provider_hours_are_cached_without_mutating_original_metadata(monkeypatch):
    calls = []
    HOURS_CACHE.clear()
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "test-key")
    candidate = place(1, source="tourapi", external_id="public-place", source_metadata={"contenttypeid": "39"})
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            pass
        async def get(self, url, **kwargs):
            calls.append((url, kwargs["params"]["contentTypeId"]))
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
                "response": {"body": {"items": {"item": [{"opentimefood": "11:00~20:00", "restdatefood": "월요일"}]}}}
            })
    monkeypatch.setattr("app.services.recommendation.httpx.AsyncClient", lambda **_: Client())
    service = RecommendationService(None, None)
    asyncio.run(service._enrich_hours([candidate]))
    asyncio.run(service._enrich_hours([candidate]))
    assert len(calls) == 1
    assert calls[0][1] == "39"
    assert candidate.source_metadata == {"contenttypeid": "39"}
    assert opening_windows(candidate, date(2026, 10, 19))[0] == []
    HOURS_CACHE.clear()


def test_future_trip_does_not_use_current_weather_as_future_forecast(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    captured = {}
    class Weather:
        async def forecast(self, *_):
            raise AssertionError("current weather must not be used for a future date")
    class Repository:
        async def recommendation_candidates(self, *_args, **_kwargs):
            return [place(1)]
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            pass
        async def post(self, _url, **kwargs):
            captured.update(json.loads(kwargs["json"]["messages"][1]["content"]))
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
                "choices": [{"message": {"content": json.dumps({"title": "서핑 여행", "description": "하루 코스", "stops": [{"activityId": 1, "reason": "체험"}]})}}]
            })
    monkeypatch.setattr("app.services.recommendation.httpx.AsyncClient", lambda **_: Client())
    result = asyncio.run(RecommendationService(Repository(), Weather()).recommend(body()))
    assert result["used_ai"] is True
    assert captured["weather"] is None and captured["travelDate"] == "2026-10-20"


def test_ai_cannot_omit_feasible_meal_or_rest(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    candidates = [place(1), place(4, "meal"), place(5, "sightseeing"), place(6, "rest")]
    prompt = {}
    class Repository:
        async def recommendation_candidates(self, *_args, **_kwargs):
            return candidates
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            pass
        async def post(self, _url, **kwargs):
            prompt.update(json.loads(kwargs["json"]["messages"][1]["content"]))
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
                "choices": [{"message": {"content": json.dumps({"title": "서핑", "description": "체험", "stops": [{"activityId": 1, "reason": "서핑"}]})}}]
            })
    monkeypatch.setattr("app.services.recommendation.httpx.AsyncClient", lambda **_: Client())
    result = asyncio.run(RecommendationService(Repository(), None).recommend(body()))
    assert {stop["role"] for stop in result["stops"]} == {"activity", "meal", "sightseeing", "rest"}
    assert result["used_ai"] is False
    assert {stop["role"] for stop in prompt["feasibleReferenceRoute"]} == {"activity", "meal", "sightseeing", "rest"}


def test_dated_api_validates_fields_auth_errors_and_serializes_timetable():
    from app.deps.auth import require_user
    actor = LoginUser(700123, "test@example.com")
    class Service:
        async def recommend(self, request, **_kwargs):
            if request.sigun == "오류":
                raise ApiError(503, "unavailable", "Temporarily unavailable")
            candidate = place(1)
            service = RecommendationService(None, None)
            return service._result(service._fallback([candidate], request), [candidate], request, used_ai=False)
    app.dependency_overrides[get_recommendation_service] = Service
    rate_limiter.buckets.pop(str(actor.id), None)
    payload = dict(theme="healing", region="강원특별자치도", sigun="양양군", sport="marine", availableMinutes=360, travelDate="2026-10-20", startTime="09:00")
    try:
        with TestClient(app) as client:
            assert client.post("/api/course-recommendations", json=payload).status_code == 401
            app.dependency_overrides[require_user] = lambda: actor
            response = client.post("/api/course-recommendations", json=payload)
            assert response.status_code == 200
            assert response.json()["travelDate"] == "2026-10-20"
            assert response.json()["stops"][0]["arrivalTime"] == "09:00"
            for change in ({"travelDate": "not-a-date"}, {"startTime": "25:00"}, {"startTime": "9:00"}):
                assert client.post("/api/course-recommendations", json=payload | change).status_code == 400
            error = client.post("/api/course-recommendations", json=payload | {"sigun": "오류"})
            assert error.status_code == 503 and error.json()["error"] == "unavailable"
    finally:
        app.dependency_overrides.pop(require_user, None)
        app.dependency_overrides.pop(get_recommendation_service, None)
