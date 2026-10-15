import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import mysql

from app.deps.auth import LoginUser, require_user
from app.exceptions import ApiError
from app.main import app
from app.models import ActivityCategory
from app.repositories.activity import ActivityRepository
from app.routes.recommendation import rate_limiter
from app.schemas.recommendation import CourseRecommendationRequest, CourseRecommendationResponse
from app.services.course_roles import role
from app.services.recommendation import RecommendationService, get_recommendation_service


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
                                              sigun="양양군", sport="marine", availableMinutes=360) | values))


def assert_no_timetable(result):
    assert not {"travel_date", "start_time", "waiting_minutes", "planning_notes"}.intersection(result)
    for stop in result["stops"]:
        assert not {"arrival_time", "departure_time", "waiting_minutes", "hours_status", "opening_hours", "visit_note"}.intersection(stop)


def test_one_experience_connects_meal_sightseeing_and_rest_without_timetable(monkeypatch):
    candidates = [place(1), place(2), place(3), place(4, "meal"), place(5, "sightseeing"), place(6, "rest")]
    class Repository:
        async def recommendation_candidates(self, *_args, **_kwargs):
            return candidates
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = asyncio.run(RecommendationService(Repository(), None).recommend(body()))
    assert result["used_ai"] is False
    assert {stop["role"] for stop in result["stops"]} == {"activity", "meal", "sightseeing", "rest"}
    assert sum(stop["role"] == "activity" for stop in result["stops"]) == 1
    assert result["total_estimated_minutes"] <= 360
    assert result["total_estimated_minutes"] == result["activity_minutes"] + result["travel_minutes"]
    assert_no_timetable(result)
    assert CourseRecommendationResponse.model_validate(result)


def test_multiple_surf_schools_are_not_returned_as_a_tour():
    service = RecommendationService(None, None)
    candidates = [place(1), place(2), place(3)]
    assert len(service._fallback(candidates, body())) == 1
    with pytest.raises(ValueError, match="repeats the main experience"):
        service._ai_stops([{"activityId": 1, "reason": "서핑"}, {"activityId": 2, "reason": "서핑"}], candidates, body())


def test_obsolete_dates_hours_closures_and_breaks_do_not_filter_places_or_add_waits():
    service = RecommendationService(None, None)
    candidate = place(1, source_metadata={"duration_minutes": 120, "hours": "10:00~11:00 (휴게 10:20~10:50)", "closed": "매주 월요일 휴무"})
    for request in (body(availableMinutes=120), body(availableMinutes=120, travelDate="2026-10-19", startTime="23:50")):
        stops = service._fallback([candidate], request)
        assert [stop["activity_id"] for stop in stops] == [1]
        result = service._result(stops, [candidate], request, used_ai=False)
        assert result["total_estimated_minutes"] == 120
        assert_no_timetable(result)
    assert service._fallback([candidate], body(availableMinutes=119)) == []


def test_travel_and_stay_budget_still_limits_ai_and_default_routes():
    service = RecommendationService(None, None)
    candidates = [place(1), place(2, "meal")]
    request = body(availableMinutes=180)
    assert len(service._fallback(candidates, request)) == 1
    assert len(service._ai_stops([{"activityId": p.id, "reason": "방문"} for p in candidates], candidates, request)) == 1


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


@pytest.mark.parametrize("omit_support", [False, True])
def test_ai_prompt_and_results_keep_roles_but_no_dates_hours_or_extra_provider_calls(monkeypatch, omit_support):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "unused-test-key")
    candidates = [place(1, source="tourapi", external_id="public-place"), place(4, "meal"), place(5, "sightseeing"), place(6, "rest")]
    captured = {}
    class Repository:
        async def recommendation_candidates(self, *_args, **_kwargs):
            return candidates
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            pass
        async def get(self, *_args, **_kwargs):
            raise AssertionError("Recommendation must not request provider operating hours")
        async def post(self, _url, **kwargs):
            captured.update(json.loads(kwargs["json"]["messages"][1]["content"]))
            chosen = candidates[:1] if omit_support else candidates
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
                "choices": [{"message": {"content": json.dumps({"title": "서핑 여행", "description": "주변 장소 연결", "stops": [{"activityId": p.id, "reason": "방문"} for p in chosen]})}}]
            })
    monkeypatch.setattr("app.services.recommendation.httpx.AsyncClient", lambda **_: Client())
    result = asyncio.run(RecommendationService(Repository(), None).recommend(body(travelDate="2026-10-20", startTime="09:00")))
    assert result["used_ai"] is not omit_support
    assert {stop["role"] for stop in result["stops"]} == {"activity", "meal", "sightseeing", "rest"}
    assert {stop["role"] for stop in captured["feasibleReferenceRoute"]} == {"activity", "meal", "sightseeing", "rest"}
    assert not {"travelDate", "startTime"}.intersection(captured)
    assert all(not {"openingHours", "closedDays"}.intersection(p) for p in captured["candidates"])
    assert all(not {"arrivalTime", "departureTime"}.intersection(p) for p in captured["feasibleReferenceRoute"])
    assert_no_timetable(result)


def test_api_serializes_no_timetable_and_preserves_auth_validation_and_errors():
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
    payload = body().model_dump(by_alias=True, exclude_unset=True)
    try:
        with TestClient(app) as client:
            assert client.post("/api/course-recommendations", json=payload).status_code == 401
            app.dependency_overrides[require_user] = lambda: actor
            for extra in ({}, {"travelDate": "2026-10-20", "startTime": "09:00"}):
                response = client.post("/api/course-recommendations", json=payload | extra)
                assert response.status_code == 200
                data = response.json()
                assert not {"travelDate", "startTime", "waitingMinutes", "planningNotes"}.intersection(data)
                assert data["stops"][0]["role"] == "activity"
                assert not {"arrivalTime", "departureTime", "hoursStatus", "openingHours"}.intersection(data["stops"][0])
            assert client.post("/api/course-recommendations", json=payload | {"availableMinutes": 0}).status_code == 400
            error = client.post("/api/course-recommendations", json=payload | {"sigun": "오류"})
            assert error.status_code == 503 and error.json()["error"] == "unavailable"
    finally:
        app.dependency_overrides.pop(require_user, None)
        app.dependency_overrides.pop(get_recommendation_service, None)
