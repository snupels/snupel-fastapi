import asyncio

import pytest

from app.jobs.sync_tourism import TourismSync, tourism_item


def place(title, code="A01010400", **extra):
    return {"contentid": "test", "contenttypeid": "12", "cat3": code,
            "title": title, "addr1": "강원특별자치도 인제군", "mapy": "38.12",
            "mapx": "128.46", **extra}


@pytest.mark.parametrize("title,code", [
    ("설악산국립공원", "A01010100"), ("태백산 국립공원", "A01010100"),
    ("치악산국립공원", "A01010100"), ("가리왕산", "A01010400"),
    ("함백산", "A01010400"), ("점봉산", "A01010400"),
    ("민둥산", "A01010400"), ("백덕산", "A01010400"), ("응봉", "A01010400"),
])
def test_source_classified_mountains_need_no_invented_course(title, code):
    row = place(title, code, overview="관광공사 산 소개<br>원문")
    value = tourism_item(row)
    assert value["category"] == "sports" and value["sport_name"] == "hiking"
    assert value["summary"] == "관광공사 산 소개\n원문"
    assert value["place_name"] == title and value["external_id"] == "test"
    assert value["latitude"] and value["longitude"]
    assert "hiking_routes" not in value["source_metadata"]
    assert tourism_item(row | {"addr1": "경기도 가평군"})["category"] == "tour"


@pytest.mark.parametrize("title,code,extra", [
    ("설악산 식당", "A05020100", {"contenttypeid": "39"}),
    ("태백산 펜션", "B02010700", {"contenttypeid": "32"}),
    ("산 캠핑장", "A03021700", {"contenttypeid": "28"}),
    ("가리왕산케이블카", "A02030400", {}),
    ("산림교육관", "A01010400", {}),
    ("일반 도시공원", "A02020700", {}),
    ("계곡 물놀이장", "A01010900", {"overview": "여름 물놀이와 휴식"}),
    ("호수 생태공원", "A01010500", {"overview": "평지 생태 탐방로와 산책"}),
])
def test_unrelated_businesses_and_nature_are_not_hiking(title, code, extra):
    assert tourism_item(place(title, code, **extra))["sport_name"] is None


def test_valley_needs_source_evidence_and_preserves_original_route_text():
    row = place("설악산 흘림골", "A01010900")
    assert tourism_item(row)["category"] == "tour"
    assert tourism_item(row | {"overview": "계곡을 따라 이어지는 탐방로 안내"})["sport_name"] == "hiking"
    class Sync(TourismSync):
        async def _get(self, url, params):
            return {"response": {"body": {"items": {"item": [
                {"infoname": "탐방코스", "infotext": "입구 → 탐방길<br>원문 거리"}
            ]}, "totalCount": 1}}}
    asyncio.run(Sync(None, None, "test")._fill_hiking_routes([row], {}))
    result = tourism_item(row)
    assert result["sport_name"] == "hiking"
    assert result["source_metadata"]["hiking_routes"][0]["infoname"] == "탐방코스"
    assert result["summary"] == "탐방코스\n입구 → 탐방길\n원문 거리"


def test_supplemental_scan_includes_imageless_mountains_without_duplicates():
    calls = []
    class Sync(TourismSync):
        async def _pages(self, url, params):
            calls.append(params)
            if params["arrange"] == "Q":
                return [place("기존 산", firstimage="existing.jpg")]
            return [place("기존 산"), place("함백산", contentid="new"),
                    place("산 식당", contentid="food", contenttypeid="39")]
    rows = asyncio.run(Sync(None, None, "test")._load_places({}, "32"))
    assert len(rows) == 2 and {row["contentid"] for row in rows} == {"test", "new"}
    assert next(row for row in rows if row["contentid"] == "test")["firstimage"] == "existing.jpg"
    assert calls[1]["contentTypeId"] == "12" and calls[1]["arrange"] == "A"
