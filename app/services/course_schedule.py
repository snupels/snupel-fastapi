"""Day-trip timing from supplied hours; missing facts are never invented."""

import re
from datetime import date, datetime
from html import unescape
from zoneinfo import ZoneInfo

WEEKDAYS = "월화수목금토일"
ROLE_LABELS = {"activity": "메인 체험", "meal": "식사", "sightseeing": "관광", "rest": "휴식"}
TIME_RANGE = re.compile(r"(\d{1,2}):([0-5]\d)\s*[~～∼–—-]\s*(\d{1,2}):([0-5]\d)")


def text(value):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", str(value or "")))).strip()


def role(activity):
    metadata = getattr(activity, "source_metadata", None) or {}
    content_type = str(metadata.get("contenttypeid") or "")
    name = str(getattr(activity, "place_name", "") or "")
    if content_type == "39":
        return "rest" if "카페" in name or "커피" in name or str(metadata.get("cat3")) == "A05020900" else "meal"
    category = getattr(activity.category, "value", activity.category)
    if category == "sports" or str(getattr(activity, "sport_name", "") or "").lower() in {
        "golf", "골프", "surfing", "marine", "ski", "rafting", "kayak", "skiing",
    }:
        return "activity"
    return "sightseeing"


def travel_day(body):
    return body.travel_date or datetime.now(ZoneInfo("Asia/Seoul")).date()


def start_minutes(body):
    hour, minute = map(int, body.start_time.split(":"))
    return hour * 60 + minute


def clock(minutes):
    return f"{minutes // 60:02}:{minutes % 60:02}"


def hours_info(activity):
    metadata = getattr(activity, "source_metadata", None) or {}
    supplied = getattr(activity, "recommendation_hours", None) or {}
    def pick(keys):
        return next((text(supplied.get(key) or metadata.get(key)) for key in keys
                     if supplied.get(key) or metadata.get(key)), "")
    return {
        "hours": pick(("hours", "opening_hours", "opentimefood", "usetimeleports", "usetimeculture", "usetime", "운영시간")),
        "closed": pick(("closed", "closed_days", "restdatefood", "restdateleports", "restdateculture", "restdate", "휴무일")),
        "by_weekday": metadata.get("opening_hours_by_weekday"),
    }


def closed_on(closed, day):
    if not closed or closed in {"연중무휴", "없음", "무휴"}:
        return False
    if re.search(r"매월|격주|공휴일|명절|설날|추석|둘째|넷째|첫째|셋째|다섯째", closed):
        return None
    compact = re.sub(r"매주|요일|휴무|휴일|정기|\s", "", closed)
    if compact and re.fullmatch(r"[월화수목금토일,·/]+", compact):
        return WEEKDAYS[day.weekday()] in compact
    return None


def opening_windows(activity, day: date):
    info = hours_info(activity)
    raw, closed = info["hours"], info["closed"]
    if isinstance(info["by_weekday"], dict):
        raw = text(info["by_weekday"].get(str(day.weekday()), raw))
        if raw in {"휴무", "closed"}:
            return [], info
    # Do not turn "second Monday" or public-holiday rules into an every-week closure.
    if closed_on(closed, day) is True:
        return [], info
    if "24시간" in raw or "상시개방" in raw.replace(" ", ""):
        return [(0, 1440)], info
    # Mixed seasonal/weekday paragraphs cannot safely be reduced to one opening interval.
    if re.search(r"평일|주말|요일|\d\s*월", raw):
        return None, info
    matches = list(TIME_RANGE.finditer(raw))
    if not matches:
        return None, info
    windows, breaks = [], []
    for index, match in enumerate(matches):
        sh, sm, eh, em = map(int, match.groups())
        begin, end = sh * 60 + sm, eh * 60 + em
        if not (0 <= begin < end <= 1440):
            return None, info  # overnight hours need a date-aware provider format
        prefix = raw[matches[index - 1].end() if index else 0:match.start()]
        (breaks if re.search(r"브레이크|break|휴게", prefix, re.I) else windows).append((begin, end))
    for break_start, break_end in breaks:
        windows = [part for begin, end in windows for part in
                   ((begin, min(end, break_start)), (max(begin, break_end), end)) if part[0] < part[1]]
    return windows or None, info


def schedule(sequence, body, minutes_for, travel_for, *, main_id):
    current = start_minutes(body)
    deadline = min(current + body.available_minutes, 1440)
    day = travel_day(body)
    result, previous = [], None
    for activity in sequence:
        starts = getattr(activity, "starts_at", None)
        ends = getattr(activity, "ends_at", None)
        if (starts and day < starts.date()) or (ends and day > ends.date()):
            return None
        travel = 0 if previous is None else travel_for(previous, activity)
        if travel is None:
            return None
        earliest = current + travel
        duration = minutes_for(activity)
        stop_role = "activity" if activity.id == main_id else role(activity)
        windows, info = opening_windows(activity, day)
        if windows == []:
            return None
        # Lunch/dinner are planning preferences, not assertions about restaurant opening hours.
        preferred = [(660, 900), (1020, 1260)] if stop_role == "meal" else [(0, 1440)]
        candidates = []
        for opening, closing in windows if windows is not None else [(0, 1440)]:
            for begin, end in preferred:
                arrival = max(earliest, opening, begin)
                departure = arrival + duration
                if departure <= min(closing, end, deadline) and arrival - earliest <= 60:
                    candidates.append((arrival, departure))
        if not candidates:
            return None
        arrival, departure = min(candidates)
        known = windows is not None and closed_on(info["closed"], day) is not None
        result.append({
            "activity_id": activity.id,
            "role": stop_role,
            "arrival_time": clock(arrival),
            "departure_time": clock(departure),
            "waiting_minutes": arrival - earliest,
            "hours_status": "provided" if known else "unknown",
            "opening_hours": info["hours"] or None,
            "visit_note": (
                "제공된 운영시간 안에 체류하도록 구성했습니다. 예약·임시휴무는 방문 전 확인해 주세요."
                if known else "운영시간·휴무일을 확인하지 못했어요. 방문 전 공식 안내처에 확인해 주세요."
            ),
        })
        current, previous = departure, activity
    return result
