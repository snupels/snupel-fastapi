import asyncio
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects import mysql

from app.jobs.sync_tourism import TourismSync, in_gangwon
from app.main import app
from app.models import Activity
from app.place_quality import VERIFIED_PLACE_NAMES, display_address, gangwon_address_status
from app.repositories.activity import ActivityRepository
from app.schemas.activity import ActivityResponse
from app.schemas.course import CourseItineraryStop
from app.schemas.recommendation import RecommendedStop
from app.services.activity import get_activity_service


@pytest.mark.parametrize(("raw", "expected"), [
    (None, None), ("", ""),
    ("강월특별자치도 춘천시 신동면", "강원특별자치도 춘천시 신동면"),
    (" 강월특별자치도 양양군", " 강원특별자치도 양양군"),
    ("강원도 강릉시", "강원도 강릉시"),
    ("강월특별자치도라는 상호", "강월특별자치도라는 상호"),
])
def test_address_display_only_corrects_known_province_typo(raw, expected):
    assert display_address(raw) == expected


def test_all_place_response_types_preserve_source_and_serialize_correct_address():
    raw = "강월특별자치도 춘천시 신동면"
    common = dict(address=raw, latitude=None, longitude=None, place_name="산소길")
    activity = ActivityResponse(
        **common, id=1, category="sports", sport_name="trekking", region="강원특별자치도",
        representative_image_url=None, created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1), source_metadata={"raw_address": raw},
    )
    itinerary = CourseItineraryStop(
        **common, position=0, stamp_id=1, activity_id=1, category="sports",
        sport_name="trekking", estimated_minutes=60,
    )
    recommended = RecommendedStop(
        **common, activity_id=1, representative_image_url=None, reason="숲길", estimated_minutes=60,
    )
    for response in (activity, itinerary, recommended):
        assert response.model_dump(by_alias=True)["address"] == "강원특별자치도 춘천시 신동면"
        assert response.address == raw
    assert activity.model_dump(by_alias=True)["metadata"] == {"raw_address": raw}


@pytest.mark.parametrize("address", ["경북 울진군", "경상북도 울진군", "경남 고성군", "울진군", "경기도 가평군"])
def test_explicit_outside_address_beats_description_and_bounding_box(address):
    assert gangwon_address_status(address) is False
    assert not in_gangwon({
        "address": address, "crsContents": "강원도와 이어지는 길", "lat": 37.2, "lon": 128.1,
    })


@pytest.mark.parametrize("address", ["강원특별자치도 고성군", "강원도 양양군", "강월특별자치도 철원군", "강릉시"])
def test_gangwon_administrative_address_is_accepted_without_coordinates(address):
    assert in_gangwon({"sigun": address})


def test_descriptive_gangwon_mentions_are_not_location_evidence():
    assert not in_gangwon({"crsContents": "강원도에서 이어지는 해파랑길", "lat": 36.99, "lon": 129.4})
    assert gangwon_address_status("고성군") is None


def discovery_ids(rows, stamp_ids=(), *, limit=None, offset=0):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("""CREATE TABLE activities (
            id INTEGER PRIMARY KEY, category TEXT, address TEXT, sigun TEXT, place_name TEXT,
            source TEXT, is_active BOOLEAN, upstream_visible BOOLEAN, ends_at DATETIME
        )"""))
        conn.execute(text("CREATE TABLE stamps (id INTEGER PRIMARY KEY, activity_id INTEGER)"))
        for row in rows:
            values = dict(category="sports", address="강원도 양양군 현남면 인구길 56-2 3층",
                          sigun="양양군", place_name="리틀코브", source="gangwon_marine_facility",
                          is_active=True, upstream_visible=True, ends_at=None) | row
            conn.execute(text("INSERT INTO activities VALUES (:id, :category, :address, :sigun, "
                              ":place_name, :source, :is_active, :upstream_visible, :ends_at)"), values)
        for index, activity_id in enumerate(stamp_ids):
            conn.execute(text("INSERT INTO stamps VALUES (:id, :activity_id)"),
                         {"id": index + 1, "activity_id": activity_id})
        query = select(Activity.id).where(ActivityRepository._available()).order_by(Activity.id)
        # Also exercise the production MySQL compiler, including correlated EXISTS statements.
        query.compile(dialect=mysql.dialect())
        result = list(conn.scalars(query.limit(limit).offset(offset)))
        assert conn.scalar(text("SELECT count(*) FROM activities")) == len(rows)
    engine.dispose()
    return result


def test_visibility_filters_before_pagination_without_deleting_rows():
    rows = [
        {"id": 1, "place_name": "양양서핑 리틀코브", "source": "gangwon_marine",
         "address": "양양군 현남면 인구길 56-2 3층"},
        {"id": 2, "place_name": "해파랑길 28코스", "source": "durunubi",
         "address": "경북 울진군", "sigun": "울진군"},
        {"id": 3},
        {"id": 4, "place_name": "다른 체험업체"},  # same building, distinct business
        {"id": 5, "address": "강원도 양양군 현남면 인구길 56-2 2층"},  # different floor
        {"id": 6, "place_name": None, "address": None, "sigun": None},
        {"id": 7, "place_name": "고성 관광지", "address": "경남 고성군", "sigun": "고성군"},
    ]
    assert discovery_ids(rows) == [3, 4, 5, 6]
    assert discovery_ids(rows, limit=2) == [3, 4]
    assert discovery_ids(rows, limit=2, offset=2) == [5, 6]


def test_duplicate_selection_prefers_stamp_link_and_keeps_other_branches():
    rows = [{"id": 1, "place_name": "양양서핑 리틀코브", "source": "gangwon_marine"}, {"id": 2}]
    assert discovery_ids(rows) == [2]
    assert discovery_ids(rows, stamp_ids=[1]) == [1]
    assert discovery_ids(rows, stamp_ids=[1, 2]) == [2]
    assert discovery_ids([rows[0], rows[1] | {"is_active": False}]) == [1]
    assert discovery_ids([rows[0], rows[1] | {"upstream_visible": False}]) == [1]
    assert discovery_ids([rows[0], rows[1] | {"address": "강원도 양양군 현남면 인구길 99"}]) == [1, 2]
    assert discovery_ids([row | {"address": "강원도 양양군 현남면"} for row in rows]) == [1, 2]


@pytest.mark.parametrize("names", VERIFIED_PLACE_NAMES)
def test_verified_name_variants_require_the_same_full_address(names):
    rows = [{"id": 1, "place_name": names[0]},
            {"id": 2, "place_name": names[1], "source": "gangwon_marine"}]
    assert discovery_ids(rows) == [1]
    assert discovery_ids([rows[0], rows[1] | {"address": "양양군 현남면 인구길 99"}]) == [1, 2]
    assert discovery_ids([rows[0], rows[1] | {"place_name": names[0] + "카페"}]) == [1, 2]


def test_geocoding_uses_corrected_query_but_preserves_upstream_address(monkeypatch):
    monkeypatch.setenv("KAKAO_CLIENT_ID", "test-key")
    calls = []

    class Client:
        async def get(self, _url, *, params, headers):
            calls.append(params)
            class Response:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"documents": [{"y": "37.8", "x": "127.8"}]}
            return Response()

    row = {"address": "강월특별자치도 춘천시 신동면", "latitude": None, "longitude": None}
    asyncio.run(TourismSync(Client(), None, "test-key")._fill_locations([row]))
    assert calls == [{"query": "강원특별자치도 춘천시 신동면"}]
    assert row["address"] == "강월특별자치도 춘천시 신동면"
    assert row["latitude"] is not None


def test_public_explore_route_serializes_address_without_rewriting_service_data():
    raw = dict(id=1, category="sports", representative_image_url=None, sport_name="trekking",
               region="강원특별자치도", place_name="산소길", latitude=None, longitude=None,
               address="강월특별자치도 춘천시", themes=[], has_mission=False,
               created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1))

    class Service:
        async def explore(self, **filters):
            return [raw]

    app.dependency_overrides[get_activity_service] = lambda: Service()
    try:
        with TestClient(app) as client:
            response = client.get("/api/sports?page=1&size=20")
        assert response.status_code == 200
        assert response.json()[0]["address"] == "강원특별자치도 춘천시"
        assert raw["address"] == "강월특별자치도 춘천시"
    finally:
        app.dependency_overrides.pop(get_activity_service, None)
