from types import SimpleNamespace

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
    stops = service._fallback(candidates, request())
    assert [stop["activity_id"] for stop in stops] == [2, 3, 4]
    assert sum(stop["estimated_minutes"] for stop in stops) <= 180
