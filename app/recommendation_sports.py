"""Shared UI-to-source sport names for recommendation selection and validation."""

SPORT_GROUPS = {
    "hiking": {"hiking", "mountaineering", "등산", "등산로"},
    "trekking": {"trekking", "walking", "트레킹", "트래킹", "걷기", "산책"},
    "marine": {"marine", "ocean", "surfing", "surf", "windsurfing", "scuba", "scuba diving", "scuba_diving", "sailing", "yacht", "yachting", "서핑", "윈드서핑", "스쿠버", "스쿠버다이빙", "요트", "해양레저", "해양 레저"},
    "ski": {"ski", "skiing", "스키", "스키장"},
    "cycling": {"cycling", "bicycle", "biking", "bike", "mtb", "자전거", "사이클", "라이딩", "산악자전거"},
    "running": {"running", "run", "marathon", "trail running", "trail_running", "러닝", "달리기", "마라톤", "트레일러닝"},
    "olympic_legacy": {"olympic_legacy", "olympic", "올림픽 레거시", "올림픽레거시"},
    "golf": {"golf", "골프"},
}


def recommendation_sport_names(sport: str) -> set[str]:
    key = sport.strip().casefold()
    return SPORT_GROUPS.get(key, {key})
