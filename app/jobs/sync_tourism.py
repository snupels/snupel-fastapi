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
PHOTO_GALLERY_URL = (
    "https://apis.data.go.kr/B551011/PhotoGalleryService1/gallerySearchList1"
)
PHOTO_KEYWORDS = {
    "ski": ("스키", "설경", "눈"),
    "golf": ("골프", "골프장"),
    "marine": ("해양", "바다", "해변", "서핑", "요트", "카약", "수상레저"),
    "trekking": ("트레킹", "걷기", "둘레길", "산소길"),
    "hiking": ("등산", "산", "정상"),
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


def match_text(value) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").lower())


def attach_tourism_photos(activities: list[dict], photos: list[dict]) -> int:
    attached = 0
    searchable_photos = [
        (
            photo,
            match_text(
                " ".join(
                    str(photo.get(key) or "")
                    for key in (
                        "galTitle",
                        "galPhotographyLocation",
                        "galSearchKeyword",
                    )
                )
            ),
        )
        for photo in photos
        if photo.get("galWebImageUrl")
    ]
    for activity in activities:
        if activity.get("representative_image_url"):
            continue
        place = match_text(activity.get("place_name"))
        area = match_text(activity.get("sigun")).removesuffix("시").removesuffix("군")
        keywords = PHOTO_KEYWORDS.get(str(activity.get("sport_name") or ""), ())
        candidates = []
        for photo, text in searchable_photos:
            score = 0
            if len(place) >= 3 and place in text:
                score += 100
            if len(area) >= 2 and area in text:
                score += 20
            if any(match_text(keyword) in text for keyword in keywords):
                score += 10
            if score >= 100 or score >= 30:
                candidates.append((score, photo))
        if not candidates:
            continue
        top_score = max(score for score, _ in candidates)
        tied = [photo for score, photo in candidates if score == top_score]
        selected = tied[int(stable_id(activity.get("place_name")), 16) % len(tied)]
        activity["representative_image_url"] = selected["galWebImageUrl"]
        metadata = dict(activity.get("source_metadata") or {})
        metadata["tourism_photo"] = {
            "content_id": selected.get("galContentId"),
            "title": selected.get("galTitle"),
            "location": selected.get("galPhotographyLocation"),
            "photographer": selected.get("galPhotographer"),
            "provider": "한국관광공사 포토코리아",
            "license": "공공누리 제1유형",
        }
        activity["source_metadata"] = metadata
        attached += 1
    return attached


def sigun(value) -> str | None:
    return next(
        (part for part in str(value or "").split() if part.endswith(("시", "군"))),
        None,
    )


def tourism_item(row: dict, category: str = "tour") -> dict:
    return {
        "external_id": str(row["contentid"]),
        "category": category,
        "place_name": row.get("title") or "",
        "representative_image_url": row.get("firstimage") or row.get("firstimage2"),
        "sport_name": None,
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

    async def _photo_gallery(self, limit: int = 1000) -> list[dict]:
        page, result = 1, []
        while len(result) < limit:
            payload = await self._get(
                PHOTO_GALLERY_URL,
                {
                    "numOfRows": min(100, limit - len(result)),
                    "pageNo": page,
                    "MobileOS": "ETC",
                    "MobileApp": "Snupel",
                    "arrange": "C",
                    "keyword": "강원",
                    "_type": "json",
                },
            )
            batch, total = items(payload)
            result.extend(batch)
            if not batch or len(result) >= total:
                break
            page += 1
        return result

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
        normalized_ski_golf = [ski_golf_item(row) for row in ski_golf]
        normalized_marine = [marine_item(row) for row in marine]
        normalized_marine_facilities = [
            marine_facility_item(row) for row in marine_facilities
        ]
        normalized_oxygen_roads = [oxygen_road_item(row) for row in oxygen_roads]
        normalized_sports = (
            normalized_ski_golf
            + normalized_marine
            + normalized_marine_facilities
            + normalized_oxygen_roads
        )
        try:
            photos = await self._photo_gallery()
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            photos = []
        photo_count = attach_tourism_photos(normalized_sports, photos)
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
            "gangwon_ski_golf", normalized_ski_golf, synced_at
        )
        result["gangwon_marine"] = await self.repository.sync_source(
            "gangwon_marine", normalized_marine, synced_at
        )
        result["gangwon_marine_facility"] = await self.repository.sync_source(
            "gangwon_marine_facility",
            normalized_marine_facilities,
            synced_at,
        )
        result["gangwon_oxygen_road"] = await self.repository.sync_source(
            "gangwon_oxygen_road",
            normalized_oxygen_roads,
            synced_at,
        )
        result["tourism_photos"] = photo_count
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
