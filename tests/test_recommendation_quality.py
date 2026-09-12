from types import SimpleNamespace
import pytest

from app.models import ActivityCategory
from app.schemas.recommendation import CourseRecommendationRequest
from app.services.recommendation import RecommendationService


def place(item_id, minutes=45, sport=None):
    return SimpleNamespace(id=item_id, place_name=f"해변 {item_id}", category=ActivityCategory.tour,
                           sport_name=sport, sigun="강릉시", region="강원특별자치도",
                           latitude=37.7, longitude=128.9, summary="휴식과 산책",
                           source_metadata={"duration_minutes": minutes})


def request(minutes=180, sport=None):
    return CourseRecommendationRequest(theme="healing", region="강원특별자치도",
                                       sigun="강릉시", availableMinutes=minutes, sport=sport)


def test_mountain_route_uses_more_conservative_distance_and_time():
    service = RecommendationService(None, None)
    first, second = place(1), place(2)
    second.latitude += 0.1
    normal_distance = service._distance_km(first, second)
    normal_minutes = service._travel_minutes(first, second)
    second.sport_name = "hiking"
    assert service._distance_km(first, second) > normal_distance
    assert service._travel_minutes(first, second) > normal_minutes


def test_over_budget_sport_cannot_anchor_a_course():
    service = RecommendationService(None, None)
    candidates = [place(1, 240, "hiking"), place(2, 30)]
    assert service._coherent_candidates(candidates, request(sport="hiking")) == []
    assert service._fallback(candidates, request(sport="hiking")) == []


def test_fallback_selects_best_feasible_route_not_longest_unbounded_route():
    service = RecommendationService(None, None)
    candidates = [place(1, 150), place(2, 60), place(3, 60), place(4, 60)]
    for candidate in candidates:
        candidate.sport_name = "walking"
    stops = service._fallback(candidates, request())
    assert [stop["activity_id"] for stop in stops] == [2, 3, 4]
    assert sum(stop["estimated_minutes"] for stop in stops) <= 180


def test_all_sports_requires_a_sports_stop_even_when_theme_prefers_scenery():
    service = RecommendationService(None, None)
    golf = place(1, 90, "golf")
    golf.place_name, golf.summary = "골프장", "골프 라운딩"
    candidates = [golf, place(2), place(3)]
    stops = service._fallback(service._coherent_candidates(candidates, request()), request())
    assert 1 in [stop["activity_id"] for stop in stops]


def test_scenery_only_course_is_not_returned():
    service = RecommendationService(None, None)
    candidates = [place(1), place(2)]
    assert service._coherent_candidates(candidates, request()) == []
    assert service._fallback(candidates, request()) == []
    with pytest.raises(ValueError, match="missing the requested sport"):
        service._ai_stops([{"activityId": 1, "reason": "풍경"}], candidates, request())


def test_korean_golf_alias_is_a_valid_anchor_and_ai_must_keep_it():
    service = RecommendationService(None, None)
    candidates = [place(1, 90, "골프"), place(2)]
    body = request(sport="golf")
    selected = service._coherent_candidates(candidates, body)
    assert selected[0].id == 1
    assert service._fallback(selected, body)[0]["activity_id"] == 1


@pytest.mark.parametrize("requested,actual", [
    ("marine", "surfing"), ("marine", "요트"),
    ("olympic_legacy", "olympic"), ("trekking", "walking"),
    ("cycling", "mtb"), ("running", "marathon"),
])
def test_ui_sport_groups_match_source_names(requested, actual):
    service = RecommendationService(None, None)
    candidates = [place(1, 90, actual), place(2)]
    body = request(sport=requested)
    selected = service._coherent_candidates(candidates, body)
    assert selected[0].id == 1
    assert service._fallback(selected, body)[0]["activity_id"] == 1
    with pytest.raises(ValueError, match="missing the requested sport"):
        service._ai_stops([{"activityId": 2, "reason": "풍경"}], selected, body)


def test_marine_does_not_treat_inland_rafting_as_marine():
    assert not RecommendationService._sports_anchor(place(1, sport="rafting"), "marine")


@pytest.mark.parametrize("sport,alias", [("golf", "골프"), ("marine", "surfing"), ("olympic_legacy", "olympic")])
def test_database_candidate_order_uses_same_sport_aliases(sport, alias):
    import asyncio
    from sqlalchemy.dialects import mysql
    from app.repositories.activity import ActivityRepository

    statements = []

    class Session:
        async def execute(self, statement):
            statements.append(statement)
            return SimpleNamespace(all=lambda: [])

    asyncio.run(ActivityRepository(Session()).recommendation_candidates(
        "강원특별자치도", None, sport, "healing",
    ))
    sql = str(statements[0].compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))
    ordering = sql.split("ORDER BY", 1)[1]
    assert f"'{alias}'" in ordering
    assert "lower(trim(activities.sport_name)) IN" in ordering
    assert "activities.category = 'sports' DESC" in ordering
