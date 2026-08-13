import asyncio
import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from sqlalchemy.dialects import mysql

from app.deps.auth import LoginUser
from app.exceptions import ApiError
from app.jobs.sync_tourism import (
    TourismSync,
    duplicate_activity_ids,
    durunubi_item,
    in_gangwon,
    items,
    marine_facility_item,
    marine_item,
    mountain_item,
    olympic_sport_categories,
    oxygen_road_item,
    ski_golf_item,
    tourism_item,
    tourism_sport,
)
from app.models import ActivityCategory, CollectedStamp, CourseTheme, SubmissionStatus
from app.repositories.activity import ActivityRepository
from app.repositories.stamp_submission import StampSubmissionRepository
from app.schemas.course import CourseCreate, CoursePatch
from app.schemas.recommendation import CourseRecommendationRequest
from app.schemas.activity import ActivityCreate, ActivityPatch
from app.schemas.stamp_submission import RejectSubmission, StampSubmissionCreate
from app.services.activity import ActivityService
from app.services.course import CourseService
from app.services.recommendation import RecommendationService
from app.services.stamp_submission import StampSubmissionService
from app.services.storage import MAX_UPLOAD_BYTES, ProofStorage
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


def test_tourapi_leports_are_normalized_as_sports_with_their_own_image():
    surf = tourism_item(
        {
            "contentid": "28",
            "contenttypeid": "28",
            "title": "양양 서핑학교",
            "addr1": "강원특별자치도 양양군 현남면",
            "cat2": "A0303",
            "cat3": "A03030100",
            "firstimage": "http://tong.visitkorea.or.kr/cms/resource/01/image.jpg",
        }
    )
    assert surf["category"] == "sports"
    assert surf["sport_name"] == "surfing"
    assert surf["representative_image_url"] == (
        "https://tong.visitkorea.or.kr/cms/resource/01/image.jpg"
    )
    assert surf["source_metadata"]["contenttypeid"] == "28"
    assert tourism_sport({"contenttypeid": "12", "title": "일반 관광지"}) is None


@pytest.mark.parametrize(
    "title",
    [
        "2018 평창동계올림픽대회 및 동계패럴림픽대회 기념관",
        "강릉올림픽뮤지엄",
    ],
)
def test_olympic_museums_are_normalized_as_legacy_sports(title):
    item = tourism_item(
        {
            "contentid": title,
            "contenttypeid": "14",
            "title": title,
            "addr1": "강원특별자치도 평창군 대관령면",
        }
    )
    assert item["category"] == "sports"
    assert item["sport_name"] == "olympic_legacy"
    assert item["source_metadata"]["sport_categories"] == ["olympic_legacy"]


@pytest.mark.parametrize(
    ("row", "sport_name"),
    [
        (
            {
                "contenttypeid": "28",
                "cat3": "A03021200",
                "title": "알펜시아리조트 스키장",
            },
            "ski",
        ),
        (
            {
                "contenttypeid": "28",
                "cat3": "A03022700",
                "title": "알펜시아 알파인코스터",
            },
            "trekking",
        ),
        (
            {"contenttypeid": "12", "title": "알펜시아리조트대관령스키역사관"},
            "olympic_legacy",
        ),
        (
            {"contenttypeid": "28", "title": "관동하키센터"},
            "ice_hockey",
        ),
    ],
)
def test_olympic_venues_can_have_snow_and_legacy_categories(row, sport_name):
    item = tourism_item({"contentid": row["title"], **row})
    assert item["category"] == "sports"
    assert item["sport_name"] == sport_name
    assert item["source_metadata"]["sport_categories"] == [
        "snow",
        "olympic_legacy",
    ]
    assert olympic_sport_categories(row) == ["snow", "olympic_legacy"]


@pytest.mark.parametrize(
    "title",
    [
        "인터컨티넨탈 알펜시아 평창 리조트",
        "홀리데이인&스위트 알펜시아 평창",
    ],
)
def test_alpensia_accommodations_are_not_normalized_as_sports(title):
    item = tourism_item({"contentid": title, "contenttypeid": "32", "title": title})
    assert item["category"] == "tour"
    assert item["sport_name"] is None
    assert "sport_categories" not in item["source_metadata"]


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"contenttypeid": 28, "cat3": "A03021200", "title": "리조트"}, "ski"),
        ({"contenttypeid": 28, "cat3": "A03022700", "title": "옛길"}, "trekking"),
        ({"contenttypeid": "28", "cat2": "A0303", "title": "수상 체험장"}, "marine"),
        ({"contenttypeid": "28", "title": "평창 MTB 파크"}, "mtb"),
        ({"contenttypeid": "28", "cat2": "A0304", "title": "비행 체험"}, "aerial"),
    ],
)
def test_tourapi_leports_sport_classification(row, expected):
    assert tourism_sport(row) == expected


@pytest.mark.parametrize(
    "row",
    [
        {"contenttypeid": "28", "cat3": "A03021700", "title": "숲속 휴양지"},
        {"contenttypeid": "28", "cat2": "A0302", "title": "별빛 글램핑"},
        {"contenttypeid": "28", "cat2": "A0305", "title": "호수 카라반"},
    ],
)
def test_tourapi_camping_and_campgrounds_are_not_sports(row):
    item = tourism_item({"contentid": "camp", **row})
    assert item["category"] == "tour"
    assert item["sport_name"] is None


@pytest.mark.parametrize(
    "title",
    [
        "철원군 병영체험수련원",
        "태백시청소년수련관",
        "강원 숲체험교육원",
        "청소년활동센터",
        "자연 체험학습장",
    ],
)
def test_tourapi_training_and_education_facilities_are_not_sports(title):
    item = tourism_item(
        {
            "contentid": title,
            "contenttypeid": "28",
            "cat2": "A0302",
            "cat3": "A03020200",
            "title": title,
        }
    )
    assert item["category"] == "tour"
    assert item["sport_name"] is None


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


def test_course_categories_require_sport_type_only_for_sports():
    assert CourseCreate(theme="healing").category == ActivityCategory.tour
    assert CourseCreate(theme="healing", category="event").category == ActivityCategory.event
    assert CourseCreate(theme="healing", category="sports", sport_name="hiking").sport_name == "hiking"
    with pytest.raises(ValueError):
        CourseCreate(theme="healing", category="sports")
    with pytest.raises(ValueError):
        CourseCreate(theme="healing", category="tour", sport_name="hiking")


def test_course_category_update_cannot_keep_sport_type_on_non_sports():
    class Repository:
        async def get(self, _item_id):
            return SimpleNamespace(category=ActivityCategory.sports, sport_name="hiking")

    with pytest.raises(ApiError):
        asyncio.run(CourseService(Repository(), "Course").update(1, CoursePatch(category="event")))


def test_tourism_sync_requests_durunubi_json():
    calls = []

    class Sync(TourismSync):
        async def _pages(self, url, params):
            calls.append((url, params))
            return [{"code": "32", "name": "강원"}] if url.endswith("/areaCode2") else []

        async def _file_rows(self, _url):
            return []

    class Repository:
        async def sync_source(self, *_):
            return 0

        async def sports_dedup_candidates(self):
            return [], set()

        async def deactivate_activity_ids(self, _ids):
            return 0

    asyncio.run(Sync(None, Repository(), "key").run())
    assert next(params for url, params in calls if "Durunubi" in url)["_type"] == "json"


def test_sports_dedup_keeps_one_preferred_source_per_place_and_area():
    rows = [
        SimpleNamespace(
            id=1,
            source="gangwon_marine",
            place_name="롱비치 서프스쿨",
            sigun="양양군",
            address="양양군 현남면",
            representative_image_url=None,
            latitude=None,
            longitude=None,
        ),
        SimpleNamespace(
            id=2,
            source="gangwon_marine_facility",
            place_name="롱비치서프스쿨",
            sigun="양양군",
            address="강원도 양양군 현남면",
            representative_image_url=None,
            latitude=38.0,
            longitude=128.0,
        ),
        SimpleNamespace(
            id=3,
            source="tourapi",
            place_name="롱비치 서프스쿨",
            sigun="양양군",
            address="강원특별자치도 양양군 현남면",
            representative_image_url="https://tong.visitkorea.or.kr/image.jpg",
            latitude=38.0,
            longitude=128.0,
        ),
        SimpleNamespace(
            id=4,
            source="tourapi",
            place_name="롱비치 서프스쿨",
            sigun="강릉시",
            address="강원특별자치도 강릉시",
            representative_image_url=None,
            latitude=None,
            longitude=None,
        ),
    ]
    assert duplicate_activity_ids(rows) == {1, 2}


def test_sports_dedup_never_hides_activity_used_by_a_stamp():
    rows = [
        SimpleNamespace(
            id=id_,
            source=source,
            place_name="문암다이브리조트",
            sigun="고성군",
            address="강원도 고성군",
            representative_image_url=image,
            latitude=None,
            longitude=None,
        )
        for id_, source, image in (
            (10, "gangwon_marine", None),
            (11, "tourapi", "https://tong.visitkorea.or.kr/image.jpg"),
        )
    ]
    assert duplicate_activity_ids(rows, {10}) == {11}


def test_file_data_download_and_gangwon_sports_normalization():
    class Response:
        def __init__(self, *, text="", content=b""):
            self.text = text
            self.content = content

    class Sync(TourismSync):
        async def _download(self, url):
            if url == "page":
                return Response(text='{"contentUrl":"https://example.com/data.csv?a=1&amp;b=2"}')
            assert url == "https://example.com/data.csv?a=1&b=2"
            return Response(
                content="상호,주소\n파도서프,강원특별자치도 양양군".encode("cp949")
            )

    assert asyncio.run(Sync(None, None, "key")._file_rows("page")) == [
        {"상호": "파도서프", "주소": "강원특별자치도 양양군"}
    ]

    ski = ski_golf_item(
        {"업소명": "설원리조트", "주소": "강원특별자치도 평창군", "업태구분명": "스키장", "영업상태": "영업/정상"}
    )
    golf = ski_golf_item(
        {"업소명": "강원CC", "주소": "강원특별자치도 춘천시", "업태구분명": "골프장"}
    )
    marine = marine_item({"시군": "양양군", "상호": "파도서프", "주소": "강원특별자치도 양양군"})
    facility = marine_facility_item(
        {"시설 코드": "1", "시설 명": "해변센터", "업종": "해양레저", "위도": "38.1", "경도": "128.6", "시군구": "고성군"}
    )
    road = oxygen_road_item({"시도명": "강원특별자치도", "시군명": "철원군", "길명칭": "쇠둘레길", "걷는거리": "27km"})
    assert ski["sport_name"] == "ski" and ski["sigun"] == "평창군"
    assert golf["sport_name"] == "golf"
    assert marine["sport_name"] == "marine" and marine["sigun"] == "양양군"
    assert str(facility["latitude"]) == "38.1" and facility["sport_name"] == "marine"
    assert road["sport_name"] == "trekking" and road["source_metadata"]["distance"] == "27km"


def test_yongpyong_ski_resort_is_snow_and_olympic_legacy():
    yongpyong = ski_golf_item(
        {
            "업소명": "용평스키장",
            "주소": "강원특별자치도 평창군 대관령면",
            "업태구분명": "스키장",
            "영업상태": "영업/정상",
        }
    )
    yongpyong_golf = ski_golf_item(
        {
            "업소명": "용평 나인골프클럽",
            "주소": "강원특별자치도 평창군 대관령면",
            "업태구분명": "골프장",
        }
    )

    assert yongpyong["sport_name"] == "ski"
    assert yongpyong["source_metadata"]["sport_categories"] == [
        "snow",
        "olympic_legacy",
    ]
    assert "sport_categories" not in yongpyong_golf["source_metadata"]


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
        recommendation_theme_match=True,
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
        "match_score": 96,
    }
    assert "latitude" not in prompt and "longitude" not in prompt and "email" not in prompt
    assert '"matchScore": 96' in prompt
    assert captured["provider"]["data_collection"] == "deny"
    Response.invalid = True
    fallback = asyncio.run(RecommendationService(Repository(), Weather()).recommend(body))
    assert fallback["used_ai"] is False
    assert fallback["match_score"] == 96
    assert fallback["stops"][0]["activity_id"] == 4
    assert "OpenRouter recommendation fallback" in caplog.text


def test_recommendation_candidates_mark_theme_matches():
    candidate = SimpleNamespace(id=4)
    statements = []

    class Result:
        def all(self):
            return [(candidate, True)]

    class Session:
        async def execute(self, statement):
            statements.append(statement)
            return Result()

    result = asyncio.run(
        ActivityRepository(Session()).recommendation_candidates(
            "강원특별자치도", "hiking", "healing"
        )
    )
    sql = str(
        statements[0].compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert result == [candidate]
    assert candidate.recommendation_theme_match is True
    assert "courses.theme = 'healing'" in sql
    assert "ORDER BY" in sql and "DESC" in sql


def test_stamp_submission_requires_owned_published_mission_and_prefix():
    class Repository:
        locks = []

        async def valid_target(self, *_, lock=False):
            self.locks.append(lock)
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
        validated = []

        def validate(self, object_key):
            self.validated.append(object_key)

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
    assert service.repository.locks == [False, False, True]
    assert service.storage.validated == ["proofs/1/2/x.jpg"]


def test_stamp_submission_rejects_foreign_passport_and_pending_submission():
    class Repository:
        valid = False
        is_pending = False

        async def valid_target(self, *_, **__):
            return self.valid

        async def collected(self, *_):
            return False

        async def pending(self, *_):
            return self.is_pending

    class Storage:
        def upload(self, *_):
            raise AssertionError("upload must not be called")

    repository = Repository()
    service = StampSubmissionService(repository, Storage())
    body = SimpleNamespace(passport_id=1, stamp_id=2, content_type="image/jpeg")
    user = LoginUser(7, "user@example.com")

    with pytest.raises(ApiError) as error:
        asyncio.run(service.upload_url(body, user))
    assert error.value.status == 404

    repository.valid = True
    repository.is_pending = True
    with pytest.raises(ApiError) as error:
        asyncio.run(service.upload_url(body, user))
    assert error.value.status == 409


def test_rejection_reason_is_trimmed_and_cannot_be_blank():
    assert RejectSubmission(reason="  사진이 행사와 무관합니다.  ").reason == "사진이 행사와 무관합니다."
    with pytest.raises(ValueError):
        RejectSubmission(reason="   ")


def test_proof_storage_validates_uploaded_object_metadata():
    class Client:
        metadata = {"ContentType": "image/jpeg", "ContentLength": 123}
        error = None

        def head_object(self, **_):
            if self.error:
                raise self.error
            return self.metadata

    storage = object.__new__(ProofStorage)
    storage.bucket = "proofs"
    storage.client = Client()
    storage.validate("proofs/1/2/x.jpg")

    storage.client.metadata = {
        "ContentType": "image/jpeg",
        "ContentLength": MAX_UPLOAD_BYTES + 1,
    }
    with pytest.raises(ApiError) as error:
        storage.validate("proofs/1/2/large.jpg")
    assert error.value.status == 400

    storage.client.error = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "HeadObject"
    )
    with pytest.raises(ApiError) as error:
        storage.validate("proofs/1/2/missing.jpg")
    assert error.value.status == 400


def test_approving_submission_creates_collected_stamp():
    class Session:
        def __init__(self):
            self.added = []

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

    session = Session()
    repository = StampSubmissionRepository(session)

    async def already_collected(*_):
        return True

    repository.collected = already_collected
    asyncio.run(repository.approve(row, 7))
    assert session.added == []


def test_stamp_submission_review_is_locked_and_admin_query_joins_activity():
    statements = []

    class Result:
        def all(self):
            return []

    class Session:
        async def execute(self, statement):
            statements.append(statement)
            return Result()

        async def scalar(self, statement):
            statements.append(statement)
            return None

    repository = StampSubmissionRepository(Session())
    asyncio.run(repository.list_status(SubmissionStatus.pending))
    asyncio.run(repository.get(1))
    sql = [
        str(statement.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))
        for statement in statements
    ]
    assert "JOIN stamps" in sql[0] and "JOIN activities" in sql[0]
    assert sql[1].endswith("FOR UPDATE")


def test_stamp_submission_cannot_be_reviewed_twice():
    class Repository:
        async def get(self, _):
            return SimpleNamespace(status=SubmissionStatus.rejected)

    service = StampSubmissionService(Repository(), object())
    with pytest.raises(ApiError) as error:
        asyncio.run(service.review(1, LoginUser(7, "admin@example.com")))
    assert error.value.status == 409
