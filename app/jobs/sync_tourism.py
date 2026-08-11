import asyncio
import csv
import hashlib
import io
import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import unescape

import httpx

from app.config.database import SessionLocal
from app.repositories.activity import ActivityRepository

KOR_BASE = "https://apis.data.go.kr/B551011/KorService2"
DURUNUBI_URL = "https://apis.data.go.kr/B551011/Durunubi/courseList"
MOUNTAIN_URL = (
    "https://apis.data.go.kr/B553662/top100FamtListBasiInfoService/"
    "getTop100FamtListBasiInfoList"
)
SKI_GOLF_DATA_URL = "https://www.data.go.kr/data/3045451/fileData.do"
MARINE_DATA_URL = "https://www.data.go.kr/data/3045471/fileData.do"
MARINE_FACILITY_DATA_URL = "https://www.data.go.kr/data/15111483/fileData.do"
OXYGEN_ROAD_DATA_URL = "https://www.data.go.kr/data/3045500/fileData.do"
LEPORTS_CONTENT_TYPE = "28"
EXCLUDED_LEPORTS_CODES = {"A03021700"}
EXCLUDED_LEPORTS_KEYWORDS = (
    "캠핑",
    "야영",
    "글램핑",
    "카라반",
    "수련원",
    "수련관",
    "교육원",
    "연수원",
    "청소년활동센터",
    "청소년문화의집",
    "체험학습장",
)
LEPORTS_CODE_SPORT = {
    "A03010200": "marine",
    "A03020500": "cycling",
    "A03020700": "golf",
    "A03021200": "ski",
    "A03021300": "skating",
    "A03021400": "snow_sledding",
    "A03021800": "climbing",
    "A03022200": "mtb",
    "A03022700": "trekking",
    "A03030100": "surfing",
    "A03030200": "kayak",
    "A03030300": "sailing",
    "A03030400": "scuba",
    "A03030500": "fishing",
    "A03030600": "fishing",
    "A03030700": "water_sports",
    "A03030800": "rafting",
    "A03040300": "paragliding",
    "A03050100": "multi_sports",
}
LEPORTS_KEYWORD_SPORT = (
    (("스노보드",), "snowboard"),
    (("스키", "눈썰매"), "ski"),
    (("스케이트", "빙상"), "skating"),
    (("서핑", "윈드서핑", "제트스키", "웨이크보드", "수상스키"), "surfing"),
    (("래프팅",), "rafting"),
    (("카약", "카누"), "kayak"),
    (("요트", "세일링"), "sailing"),
    (("스쿠버", "스노클"), "scuba"),
    (("골프",), "golf"),
    (("MTB", "산악자전거"), "mtb"),
    (("트레킹", "트래킹", "둘레길"), "trekking"),
    (("등산", "암벽", "클라이밍"), "climbing"),
    (("자전거", "사이클"), "cycling"),
    (("마라톤", "러닝"), "running"),
    (("패러글라이딩", "행글라이딩", "스카이다이빙"), "paragliding"),
)
SOURCE_PRIORITY = {
    "tourapi": 0,
    "durunubi": 1,
    "mountain100": 1,
    "gangwon_marine_facility": 2,
    "gangwon_marine": 3,
    "gangwon_oxygen_road": 3,
    "gangwon_ski_golf": 3,
}


def items(payload: dict) -> tuple[list[dict], int]:
    body = payload["response"]["body"]
    values = (body.get("items") or {}).get("item", [])
    if isinstance(values, dict):
        values = [values]
    return values or [], int(body.get("totalCount", len(values or [])))


def number(value) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except InvalidOperation:
        return None


def date(value) -> datetime | None:
    try:
        return datetime.strptime(str(value), "%Y%m%d") if value else None
    except ValueError:
        return None


def pick(row: dict, *names):
    return next((row[name] for name in names if row.get(name) not in (None, "")), None)


def stable_id(*values) -> str:
    raw = "|".join(str(value or "").strip() for value in values)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def normalized_place_name(value) -> str:
    text = str(value or "").lower()
    for corporate in ("주식회사", "유한회사", "(주)", "㈜"):
        text = text.replace(corporate, "")
    return re.sub(r"[^0-9a-z가-힣]", "", text)


def duplicate_area(row) -> str:
    if row.sigun:
        return normalized_place_name(row.sigun)
    match = re.search(r"([가-힣]+(?:시|군))", str(row.address or ""))
    return normalized_place_name(match.group(1)) if match else ""


def duplicate_activity_ids(rows: list, protected_ids: set[int] | None = None) -> set[int]:
    protected = protected_ids or set()
    groups: dict[tuple[str, str], list] = {}
    for row in rows:
        name, area = normalized_place_name(row.place_name), duplicate_area(row)
        if name and area:
            groups.setdefault((name, area), []).append(row)

    duplicates: set[int] = set()
    for group in groups.values():
        if len(group) < 2:
            continue
        mission_rows = [row for row in group if row.id in protected]
        candidates = mission_rows or group
        survivor = min(
            candidates,
            key=lambda row: (
                SOURCE_PRIORITY.get(str(row.source or ""), 99),
                0 if row.representative_image_url else 1,
                0 if row.latitude is not None and row.longitude is not None else 1,
                row.id,
            ),
        )
        duplicates.update(
            row.id for row in group if row.id != survivor.id and row.id not in protected
        )
    return duplicates


def sigun(value) -> str | None:
    return next(
        (part for part in str(value or "").split() if part.endswith(("시", "군"))),
        None,
    )


def tourism_sport(row: dict) -> str | None:
    if str(row.get("contenttypeid") or "") != LEPORTS_CONTENT_TYPE:
        return None
    code = str(row.get("cat3") or "").upper()
    title = str(row.get("title") or "")
    if code in EXCLUDED_LEPORTS_CODES or any(
        keyword in title for keyword in EXCLUDED_LEPORTS_KEYWORDS
    ):
        return None
    if code in LEPORTS_CODE_SPORT:
        return LEPORTS_CODE_SPORT[code]
    text = " ".join(str(row.get(key) or "") for key in ("title", "cat1", "cat2", "cat3"))
    upper_text = text.upper()
    for keywords, sport in LEPORTS_KEYWORD_SPORT:
        if any(keyword.upper() in upper_text for keyword in keywords):
            return sport
    cat2 = str(row.get("cat2") or "").upper()
    if cat2 == "A0303":
        return "marine"
    if cat2 == "A0304":
        return "aerial"
    if cat2 == "A0305":
        return "multi_sports"
    return "athletics"


def tourism_image(row: dict) -> str | None:
    value = row.get("firstimage") or row.get("firstimage2")
    if not value:
        return None
    return str(value).replace(
        "http://tong.visitkorea.or.kr/", "https://tong.visitkorea.or.kr/", 1
    )


def tourism_item(row: dict, category: str = "tour") -> dict:
    sport_name = tourism_sport(row) if category == "tour" else None
    return {
        "external_id": str(row["contentid"]),
        "category": "sports" if sport_name else category,
        "place_name": row.get("title") or "",
        "representative_image_url": tourism_image(row),
        "sport_name": sport_name,
        "region": "강원특별자치도",
        "sigun": sigun(row.get("addr1")),
        "latitude": number(row.get("mapy")),
        "longitude": number(row.get("mapx")),
        "summary": None,
        "address": " ".join(filter(None, (row.get("addr1"), row.get("addr2")))) or None,
        "source_url": None,
        "starts_at": date(row.get("eventstartdate")),
        "ends_at": date(row.get("eventenddate")),
        "source_metadata": {
            key: value
            for key, value in row.items()
            if key in {"contenttypeid", "cat1", "cat2", "cat3", "tel", "zipcode"}
        },
    }


def durunubi_item(row: dict) -> dict:
    external_id = pick(row, "crsIdx", "routeIdx", "route_idx", "crs_idx")
    return {
        "external_id": str(external_id) if external_id is not None else "",
        "category": "sports",
        "place_name": pick(row, "crsKorNm", "routeNm", "crsNm") or "",
        "representative_image_url": pick(row, "crsImg", "imageUrl", "imgUrl"),
        "sport_name": "trekking",
        "region": "강원특별자치도",
        "sigun": sigun(pick(row, "sigun", "address", "addr")),
        "latitude": number(pick(row, "crsLat", "mapy", "lat")),
        "longitude": number(pick(row, "crsLon", "mapx", "lon", "lng")),
        "summary": pick(row, "crsContents", "crsSummary", "routeInfo"),
        "address": pick(row, "sigun", "address", "addr"),
        "source_url": pick(row, "gpxPath", "gpxUrl"),
        "starts_at": None,
        "ends_at": None,
        "source_metadata": {
            "difficulty": pick(row, "crsLevel", "routeLevel"),
            "distance": pick(row, "crsDstnc", "routeLength"),
            "duration": pick(row, "crsTotlRqrmHour", "requiredTime"),
        },
    }


def mountain_item(row: dict) -> dict:
    external_id = pick(row, "mntnId", "mtnId", "mtn_id", "mountainId", "frtrlId")
    return {
        "external_id": str(external_id) if external_id is not None else "",
        "category": "sports",
        "place_name": pick(row, "mntnNm", "mtnNm", "mtn_nm", "mountainName") or "",
        "representative_image_url": None,
        "sport_name": "hiking",
        "region": "강원특별자치도",
        "sigun": sigun(pick(row, "addrNm", "ctpvNm", "addr", "address")),
        "latitude": number(pick(row, "lat", "latitude", "mntnLat", "mtnLat")),
        "longitude": number(pick(row, "lot", "lon", "longitude", "mntnLot", "mtnLon")),
        "summary": None,
        "address": pick(row, "addrNm", "ctpvNm", "addr", "address"),
        "source_url": None,
        "starts_at": None,
        "ends_at": None,
        "source_metadata": {"altitude": pick(row, "aslAltide", "altitude", "mtnHg")},
    }


def ski_golf_item(row: dict) -> dict:
    kind = str(row.get("업태구분명") or "")
    name = str(row.get("업소명") or "").strip()
    address = str(row.get("주소") or "").strip()
    sport_name = "ski" if "스키" in kind else "golf"
    return {
        "external_id": stable_id(name, address, kind),
        "category": "sports",
        "place_name": name,
        "representative_image_url": None,
        "sport_name": sport_name,
        "region": "강원특별자치도",
        "sigun": sigun(address),
        "latitude": None,
        "longitude": None,
        "summary": f"강원특별자치도 등록 {kind}",
        "address": address or None,
        "source_url": "https://www.data.go.kr/data/3045451/fileData.do",
        "starts_at": None,
        "ends_at": None,
        "source_metadata": {"business_status": row.get("영업상태"), "type": kind},
    }


def marine_item(row: dict) -> dict:
    name = str(row.get("상호") or "").strip()
    address = str(row.get("주소") or "").strip()
    return {
        "external_id": stable_id(name, address),
        "category": "sports",
        "place_name": name,
        "representative_image_url": None,
        "sport_name": "marine",
        "region": "강원특별자치도",
        "sigun": str(row.get("시군") or "").strip() or sigun(address),
        "latitude": None,
        "longitude": None,
        "summary": "강원 동해안 해양·수상레저 체험 업체",
        "address": address or None,
        "source_url": "https://www.data.go.kr/data/3045471/fileData.do",
        "starts_at": None,
        "ends_at": None,
        "source_metadata": None,
    }


def marine_facility_item(row: dict) -> dict:
    name = str(row.get("시설 명") or "").strip()
    address = str(row.get("주소") or row.get("지번 주소") or "").strip()
    return {
        "external_id": stable_id(row.get("시설 코드"), name, address),
        "category": "sports",
        "place_name": name,
        "representative_image_url": None,
        "sport_name": "marine",
        "region": str(row.get("시도") or "강원특별자치도").strip(),
        "sigun": str(row.get("시군구") or "").strip() or sigun(address),
        "latitude": number(row.get("위도")),
        "longitude": number(row.get("경도")),
        "summary": "강원 동해안 해양레저 관광시설",
        "address": address or None,
        "source_url": "https://www.data.go.kr/data/15111483/fileData.do",
        "starts_at": None,
        "ends_at": None,
        "source_metadata": {"business_type": row.get("업종"), "town": row.get("읍면동")},
    }


def oxygen_road_item(row: dict) -> dict:
    name = str(row.get("길명칭") or "").strip()
    guide = str(row.get("길도우미") or "").strip()
    return {
        "external_id": stable_id(row.get("시군명"), name),
        "category": "sports",
        "place_name": name,
        "representative_image_url": None,
        "sport_name": "trekking",
        "region": str(row.get("시도명") or "강원특별자치도").strip(),
        "sigun": str(row.get("시군명") or "").strip() or None,
        "latitude": None,
        "longitude": None,
        "summary": str(row.get("코스정보") or "강원 산소길 트레킹 코스").strip(),
        "address": guide or None,
        "source_url": "https://www.data.go.kr/data/3045500/fileData.do",
        "starts_at": None,
        "ends_at": None,
        "source_metadata": {
            "contact": row.get("문의전화"),
            "distance": row.get("걷는거리"),
            "duration": row.get("걷는시간"),
            "nearby": row.get("주변 볼거리"),
        },
    }


def in_gangwon(row: dict) -> bool:
    if "강원" in " ".join(str(value) for value in row.values() if value is not None):
        return True
    latitude = number(pick(row, "crsLat", "mapy", "lat", "latitude", "mntnLat", "mtnLat"))
    longitude = number(
        pick(row, "crsLon", "mapx", "lon", "lng", "longitude", "mntnLot", "mtnLon")
    )
    return bool(latitude and longitude and Decimal("37") <= latitude <= Decimal("38.7") and Decimal("127") <= longitude <= Decimal("129.5"))


class TourismSync:
    def __init__(self, client: httpx.AsyncClient, repository: ActivityRepository, key: str):
        self.client, self.repository, self.key = client, repository, key

    async def _get(self, url: str, params: dict) -> dict:
        for attempt in range(3):
            try:
                response = await self.client.get(url, params={"serviceKey": self.key} | params)
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError("retryable", request=response.request, response=response)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError):
                if attempt == 2:
                    raise
                await asyncio.sleep(2**attempt)
        raise RuntimeError

    async def _pages(self, url: str, params: dict) -> list[dict]:
        page, result = 1, []
        while True:
            payload = await self._get(url, params | {"pageNo": page, "numOfRows": 100})
            batch, total = items(payload)
            result.extend(batch)
            if not batch or len(result) >= total:
                return result
            page += 1

    async def _download(self, url: str):
        for attempt in range(3):
            try:
                response = await self.client.get(url)
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        "retryable", request=response.request, response=response
                    )
                response.raise_for_status()
                return response
            except httpx.HTTPError:
                if attempt == 2:
                    raise
                await asyncio.sleep(2**attempt)
        raise RuntimeError

    async def _file_rows(self, page_url: str) -> list[dict]:
        page = await self._download(page_url)
        match = re.search(r'"contentUrl"\s*:\s*"([^"]+)"', page.text)
        if not match:
            raise ValueError(f"data.go.kr download URL not found: {page_url}")
        file_response = await self._download(unescape(match.group(1)))
        try:
            content = file_response.content.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = file_response.content.decode("cp949")
        return list(csv.DictReader(io.StringIO(content)))

    async def run(self) -> dict[str, int]:
        common = {"MobileOS": "ETC", "MobileApp": "Snupel", "_type": "json"}
        codes = await self._pages(f"{KOR_BASE}/areaCode2", common)
        area_code = next(str(row["code"]) for row in codes if "강원" in row.get("name", ""))
        places = await self._pages(
            f"{KOR_BASE}/areaBasedList2", common | {"areaCode": area_code, "arrange": "Q"}
        )
        festivals = await self._pages(
            f"{KOR_BASE}/searchFestival2",
            common | {"areaCode": area_code, "eventStartDate": datetime.now().strftime("%Y%m%d")},
        )
        trails = [
            row
            for row in await self._pages(DURUNUBI_URL, common)
            if in_gangwon(row)
        ]
        mountains = [
            row
            for row in await self._pages(MOUNTAIN_URL, {"type": "json"})
            if in_gangwon(row)
        ]
        ski_golf = await self._file_rows(SKI_GOLF_DATA_URL)
        marine = await self._file_rows(MARINE_DATA_URL)
        marine_facilities = [
            row
            for row in await self._file_rows(MARINE_FACILITY_DATA_URL)
            if "해양레저" in str(row.get("업종") or "")
        ]
        oxygen_roads = await self._file_rows(OXYGEN_ROAD_DATA_URL)
        synced_at = datetime.now()
        result = {}
        result["tourapi"] = await self.repository.sync_source(
            "tourapi",
            [tourism_item(row) for row in places]
            + [tourism_item(row, "event") for row in festivals],
            synced_at,
        )
        result["durunubi"] = await self.repository.sync_source(
            "durunubi", [durunubi_item(row) for row in trails], synced_at
        )
        result["mountain100"] = await self.repository.sync_source(
            "mountain100", [mountain_item(row) for row in mountains], synced_at
        )
        result["gangwon_ski_golf"] = await self.repository.sync_source(
            "gangwon_ski_golf", [ski_golf_item(row) for row in ski_golf], synced_at
        )
        result["gangwon_marine"] = await self.repository.sync_source(
            "gangwon_marine", [marine_item(row) for row in marine], synced_at
        )
        result["gangwon_marine_facility"] = await self.repository.sync_source(
            "gangwon_marine_facility",
            [marine_facility_item(row) for row in marine_facilities],
            synced_at,
        )
        result["gangwon_oxygen_road"] = await self.repository.sync_source(
            "gangwon_oxygen_road",
            [oxygen_road_item(row) for row in oxygen_roads],
            synced_at,
        )
        candidates, protected_ids = await self.repository.sports_dedup_candidates()
        duplicate_ids = duplicate_activity_ids(candidates, protected_ids)
        result["duplicates_deactivated"] = (
            await self.repository.deactivate_activity_ids(duplicate_ids)
        )
        return result


async def main() -> None:
    key = os.getenv("DATA_GO_KR_SERVICE_KEY")
    if not key:
        raise RuntimeError("DATA_GO_KR_SERVICE_KEY is required")
    async with SessionLocal.begin() as session, httpx.AsyncClient(timeout=20) as client:
        counts = await TourismSync(client, ActivityRepository(session), key).run()
    print(" ".join(f"{source}={count}" for source, count in counts.items()))


if __name__ == "__main__":
    asyncio.run(main())
