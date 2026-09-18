"""Import verified Gangwon sections, retaining the upstream route text."""
import xml.etree.ElementTree as ET
from datetime import datetime

URL = "https://apis.data.go.kr/1400000/trailInfoService/gettrailservice"
SOURCE = "forest_baekdu"
# Verified start landmarks, not resort/mountain centroids. Unclear starts are omitted.
STARTS = {
    "BAEK_34": ("화방재", "화방재", "604996321", "태백시"),
    "BAEK_36": ("구부시령", "구부시령", "965065370", "삼척시"),
    "BAEK_37": ("댓재", "두타산 댓재분기점", "17553752", "삼척시"),
    "BAEK_38": ("고적대", "고적대", "204667856", "정선군"),
}


def parse_routes(content):
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError("Invalid trail response") from exc
    if root.findtext(".//resultCode") != "00":
        raise ValueError("Trail provider returned an error")
    rows = [{child.tag: (child.text or "").strip() for child in item}
            for item in root.findall(".//item")]
    if int(root.findtext(".//totalCount") or "0") != len(rows):
        raise ValueError("Incomplete trail response")
    return rows


def activity(row, landmark):
    expected = STARTS.get(row.get("baekduId"))
    if not expected or row.get("baekdusections") != expected[0]:
        raise ValueError("Unverified trail start")
    start, _, place_id, city = expected
    address = landmark.get("address_name", "")
    if (str(landmark.get("id")) != place_id or city not in address
            or not address.startswith(("강원특별자치도 ", "강원도 "))):
        raise ValueError("Start landmark does not match")
    lat, lon = float(landmark["y"]), float(landmark["x"])
    if not (37 <= lat <= 39 and 127 <= lon <= 130):
        raise ValueError("Invalid start coordinates")
    end, route = row.get("baekdusectione"), row.get("baekduvia")
    if not end or not route or not route.startswith(start + "→"):
        raise ValueError("Missing route information")
    detail = "\n".join(filter(None, [route,
        f"지도상 거리: {row['baekdudistance']}" if row.get("baekdudistance") else None,
        f"API 제공 구간거리: {row['baekdurealdistance']}" if row.get("baekdurealdistance") else None,
        f"주요 볼거리: {row['baekduspect']}" if row.get("baekduspect") else None]))
    return {
        "external_id": row["baekduId"], "category": "sports", "sport_name": "hiking",
        "place_name": f"백두대간 {start}~{end} 코스", "region": "강원특별자치도",
        "sigun": city, "latitude": lat, "longitude": lon, "address": address,
        "representative_image_url": None, "source_url": None,
        "summary": "백두대간 종주 구간입니다. 지도는 구간 출발점이며 주차장이나 차량 접근 지점을 뜻하지 않습니다. "
                   "소요 시간·난이도·현재 개방 여부는 제공되지 않으므로 출발 전 관리기관의 통제 안내를 확인하세요.",
        "source_metadata": {"hiking_routes": [{"infoname": "등산 코스", "infotext": detail}],
                            "upstream": row, "coordinate_type": "route_start",
                            "coordinate_source": "kakao", "coordinate_place_id": place_id},
    }


async def sync(client, repository, service_key, kakao_key):
    if not kakao_key:
        raise ValueError("Start lookup key is required")
    response = await client.get(URL, params={"serviceKey": service_key,
                                           "numOfRows": 100, "pageNo": 1})
    response.raise_for_status()
    rows = parse_routes(response.content)
    selected = {row["baekduId"]: row for row in rows if row.get("baekduId") in STARTS}
    if set(selected) != set(STARTS):
        raise ValueError("Expected sections missing; keeping existing records")
    items = []
    for identifier, row in selected.items():
        _, query, place_id, _ = STARTS[identifier]
        result = await client.get("https://dapi.kakao.com/v2/local/search/keyword.json",
                                  params={"query": query},
                                  headers={"Authorization": f"KakaoAK {kakao_key}"})
        result.raise_for_status()
        landmark = next((place for place in result.json().get("documents", [])
                         if str(place.get("id")) == place_id), None)
        if landmark is None:
            raise ValueError("Verified start not found; keeping existing records")
        items.append(activity(row, landmark))
    return await repository.sync_source(SOURCE, items, datetime.now())
