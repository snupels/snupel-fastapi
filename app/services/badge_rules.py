"""Evaluate badges using facts of fully approved missions, never raw stamp totals."""

import json
from pathlib import Path


SPORT_ALIASES = {
    "hiking": {"hiking", "mountaineering", "등산", "등산로"},
    "trekking": {"trekking", "walking", "trail walking", "트레킹", "트래킹", "걷기", "산책"},
    "running": {"running", "run", "marathon", "trail running", "trail_running", "러닝", "달리기", "마라톤", "트레일러닝"},
    "cycling": {"cycling", "bicycle", "biking", "bike", "mtb", "자전거", "사이클", "라이딩", "산악자전거"},
    "ski": {"ski", "skiing", "스키", "스키장"},
    "snowboard": {"snowboard", "snowboarding", "스노보드", "스노우보드"},
    "surfing": {"surfing", "surf", "서핑"},
    "windsurfing": {"windsurfing", "윈드서핑"},
    "scuba": {"scuba", "scuba diving", "scuba_diving", "스쿠버", "스쿠버다이빙"},
    "canoe": {"canoe", "canoeing", "카누"},
    "kayak": {"kayak", "kayaking", "카약"},
    "rafting": {"rafting", "래프팅", "레프팅"},
    "wakeboard": {"wakeboard", "wakeboarding", "웨이크보드"},
    "waterski": {"waterski", "water skiing", "water_ski", "수상스키"},
    "sailing": {"sailing", "yacht", "yachting", "요트", "세일링"},
    "zipline": {"zipline", "zipwire", "zip wire", "짚라인", "짚와이어"},
    "paragliding": {"paragliding", "패러글라이딩"},
    "railbike": {"railbike", "rail bike", "레일바이크"},
    "skating": {"skating", "ice skating", "ice_skating", "스케이트", "스케이팅"},
    "golf": {"golf", "골프"},
    "swimming": {"swimming", "수영"},
    "climbing": {"climbing", "클라이밍", "암벽등반"},
}
_NORMALIZED_SPORTS = {alias: sport for sport, aliases in SPORT_ALIASES.items() for alias in aliases}

# The original mission definitions explicitly require these experiences. Match
# both their exact title and original API identity, not just a place name or a
# broad API category (some railbike/zipline places are incorrectly 'trekking').
_VERIFIED_BY_TITLE = {
    "아리힐스 짚와이어 체험 인증": ("zipline", None),
    "하늘나르기 짚라인 체험 인증": ("zipline", None),
    "조나단 패러글라이딩 체험 인증": ("paragliding", None),
    "오크밸리 스키·보드 체험 인증": ("ski", None),
    "비발디파크 스키·보드 체험 인증": ("ski", None),
    "하이원 스키·보드 체험 인증": ("ski", None),
    "오투리조트 스키·보드 체험 인증": ("ski", None),
    "알펜시아 스키·보드 체험 인증": ("ski", None),
    "물레길 카누 체험 인증": ("canoe", "inland"),
    "서피비치 서핑 체험 인증": ("surfing", "marine"),
    "송강카누학교 카누 체험 인증": ("canoe", "inland"),
    "코마린요트 승선 체험 인증": ("sailing", "marine"),
    "연대천래프팅 체험 인증": ("rafting", "inland"),
    "한탄강 래프팅 체험 인증": ("rafting", "inland"),
    "킹서프 서핑 체험 인증": ("surfing", "marine"),
    "김유정 레일바이크 체험 인증": ("railbike", None),
    "정동진 레일바이크 체험 인증": ("railbike", None),
    "정선 레일바이크 체험 인증": ("railbike", None),
    "오대산 선재길 걷기 인증": ("trekking", None),
    "파로호 자전거길 라이딩 인증": ("cycling", None),
    "송지호 산소길 걷기 인증": ("trekking", None),
    "동해 해안누리길 걷기 인증": ("trekking", None),
    "횡성 태종대길 걷기 인증": ("trekking", None),
    "강릉올림픽뮤지엄 방문 인증": (None, None),
}
_DEFINITIONS = json.loads((Path(__file__).parents[1] / "data/photo_missions.json").read_text(encoding="utf-8"))
VERIFIED_MISSION_SPORTS = {
    (item["title"], item["source"], item["externalId"]): _VERIFIED_BY_TITLE[item["title"]]
    for item in _DEFINITIONS if item["title"] in _VERIFIED_BY_TITLE
}


def normalize_sport(value: str | None) -> str | None:
    return _NORMALIZED_SPORTS.get(value.strip().casefold()) if value else None


def mission_sport(fact) -> tuple[str | None, str | None]:
    key = (fact.get("course_title"), fact.get("source"), fact.get("external_id"))
    if key in VERIFIED_MISSION_SPORTS:
        return VERIFIED_MISSION_SPORTS[key]
    if str(fact.get("course_sport") or "").strip().casefold() in {"olympic", "올림픽 레거시"}:
        return None, None
    sport = normalize_sport(fact.get("course_sport")) or normalize_sport(fact.get("activity_sport"))
    # Generic WATER, SNOW, canoe/kayak, diving or boards alone do not establish
    # the environment. Verified mission identities resolve those ambiguities.
    setting = "marine" if sport == "surfing" else "inland" if sport == "rafting" else None
    return sport, setting


def badge_progress(facts) -> dict[str, int]:
    groups = {name: set() for name in ("missions", "mountains", "trekking", "marine", "inland_water", "snow", "cycling", "running")}
    sports = set()
    for fact in facts:
        mission_id = fact["course_id"]
        groups["missions"].add(mission_id)
        if fact.get("mountain"):
            groups["mountains"].add(mission_id)
        sport, setting = mission_sport(fact)
        if sport:
            sports.add(sport)
        if sport in {"trekking", "cycling", "running"}:
            groups[sport].add(mission_id)
        if sport in {"ski", "snowboard"}:
            groups["snow"].add(mission_id)
        if setting == "marine":
            groups["marine"].add(mission_id)
        elif setting == "inland":
            groups["inland_water"].add(mission_id)
    return {name: len(values) for name, values in groups.items()} | {"sports": len(sports)}


def earned_badge_rules(facts) -> set[str]:
    progress = badge_progress(facts)
    thresholds = {
        "first_mission": ("missions", 1), "first_mountain": ("mountains", 1),
        "three_missions": ("missions", 3), "three_sports": ("sports", 3),
        "trekking_three": ("trekking", 3), "first_marine": ("marine", 1),
        "first_inland_water": ("inland_water", 1), "first_snow": ("snow", 1),
        "first_cycling": ("cycling", 1), "first_running": ("running", 1),
    }
    # 1000m summits and sunrise require explicit mission-specific evidence;
    # none of the current registered photo missions requires those proofs.
    return {rule for rule, (metric, minimum) in thresholds.items() if progress[metric] >= minimum}
