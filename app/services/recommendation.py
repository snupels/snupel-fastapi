import asyncio
import json
import logging
import math
import os
import random
import time
from datetime import datetime
from itertools import permutations
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import httpx
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.exceptions import ApiError
from app.repositories.activity import ActivityRepository
from app.repositories.course import CourseRepository
from app.services.weather import WeatherService, get_weather_service
from app.services.badge_rules import normalize_sport
from app.recommendation_sports import recommendation_sport_names
from app.services.course_schedule import (
    ROLE_LABELS, hours_info, role, schedule, travel_day,
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_LEG_KM = 40
AVERAGE_KPH = 40
ROAD_DISTANCE_FACTOR = 1.3
MOUNTAIN_ROAD_DISTANCE_FACTOR = 1.6
MAX_COHERENT_CANDIDATES = 30
MAX_AI_CANDIDATES = 10
MIN_THEME_CANDIDATES = 3
WEATHER_TIMEOUT_SECONDS = 2
AI_TIMEOUT_SECONDS = 12
DEFAULT_AI_MODEL = "deepseek/deepseek-chat-v3.1"
DEFAULT_AI_FALLBACK_MODEL = "deepseek/deepseek-v3.1-terminus"
CATEGORY_MINUTES = {"tour": 45, "sports": 90, "event": 60}
HOURS_CACHE = {}
THEME_LABELS = {
    "healing": "힐링",
    "thrill": "스릴",
    "photo_spot": "포토스팟",
    "stamp": "스탬프",
}
THEME_KEYWORDS = {
    "healing": (
        "해변",
        "공원",
        "숲",
        "산책",
        "명상",
        "휴양",
        "수목원",
        "호수",
        "정자",
        "카페",
        "계곡",
    ),
    "thrill": (
        "카누",
        "카약",
        "래프팅",
        "서핑",
        "스키",
        "산악",
        "등산",
        "레저",
        "패러",
        "짚",
        "클라이밍",
    ),
    "photo_spot": (
        "해변",
        "전망",
        "공원",
        "산",
        "길",
        "마을",
        "정자",
        "폭포",
        "호수",
        "계곡",
        "숲",
        "정원",
        "바다",
        "섬",
    ),
    "stamp": ("스탬프", "도장"),
}
logger = logging.getLogger(__name__)


class RecommendationService:
    @staticmethod
    def _sports_anchor(activity, sport=None) -> bool:
        actual = str(getattr(activity, "sport_name", "") or "").strip().casefold()
        if sport:
            requested = str(sport).strip().casefold()
            return actual in recommendation_sport_names(requested) or (
                normalize_sport(actual) is not None
                and normalize_sport(actual) == normalize_sport(requested)
            )
        return (
            getattr(activity.category, "value", activity.category) == "sports"
            or normalize_sport(actual) is not None
            or actual in recommendation_sport_names("olympic_legacy")
            or actual in recommendation_sport_names("marine")
        )

    def __init__(
        self,
        repository: ActivityRepository,
        weather: WeatherService,
        course_repository: CourseRepository | None = None,
    ) -> None:
        self.repository = repository
        self.weather = weather
        self.course_repository = course_repository

    @staticmethod
    def _minutes(activity) -> int:
        metadata = activity.source_metadata or {}
        category = getattr(activity.category, "value", activity.category)
        try:
            default = {"meal": 60, "rest": 30}.get(role(activity), CATEGORY_MINUTES[category])
            sport = str(getattr(activity, "sport_name", "") or "").lower()
            if role(activity) == "activity":
                default = 240 if sport in {"golf", "골프"} else 120 if sport in {"marine", "surfing", "서핑"} else default
            return max(1, int(metadata.get("duration_minutes", default)))
        except (KeyError, TypeError, ValueError):
            return 60

    @staticmethod
    def _mountainous(activity) -> bool:
        sport = str(getattr(activity, "sport_name", "") or "").lower()
        name = str(getattr(activity, "place_name", "") or "")
        return sport in {"hiking", "mountain", "ski", "snowboard", "등산", "스키", "산악"} or any(
            word in name for word in ("스키장", "등산", "산악")
        )

    @staticmethod
    def _distance_km(first, second) -> float | None:
        if first.id == second.id:
            return 0
        if all(
            value is not None
            for value in (first.latitude, first.longitude, second.latitude, second.longitude)
        ):
            lat1, lon1 = math.radians(float(first.latitude)), math.radians(float(first.longitude))
            lat2, lon2 = math.radians(float(second.latitude)), math.radians(float(second.longitude))
            delta_lat, delta_lon = lat2 - lat1, lon2 - lon1
            value = (
                math.sin(delta_lat / 2) ** 2
                + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
            )
            straight_line_km = 6371 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))
            factor = (
                MOUNTAIN_ROAD_DISTANCE_FACTOR
                if RecommendationService._mountainous(first) or RecommendationService._mountainous(second)
                else ROAD_DISTANCE_FACTOR
            )
            return straight_line_km * factor
        if first.sigun and first.sigun == second.sigun:
            return 10
        return None

    def _travel_minutes(self, first, second) -> int | None:
        distance = self._distance_km(first, second)
        if distance is None or distance > MAX_LEG_KM:
            return None
        return 0 if not distance else max(10, math.ceil(distance / AVERAGE_KPH * 60))

    @staticmethod
    def _theme_relevance(activity, theme: str) -> int:
        if bool(getattr(activity, "recommendation_theme_match", False)):
            return 2
        category = getattr(activity.category, "value", activity.category)
        if theme == "thrill" and category == "sports":
            return 1
        text = " ".join(filter(None, (activity.place_name, activity.summary))).lower()
        return int(any(keyword in text for keyword in THEME_KEYWORDS[theme]))

    @staticmethod
    def _recommendable(activity) -> bool:
        content_type = str((activity.source_metadata or {}).get("contenttypeid") or "")
        return content_type not in {"32", "38"} and not (
            content_type == "15"
            and getattr(activity, "starts_at", None) is None
            and getattr(activity, "ends_at", None) is None
        )

    def _coherent_candidates(self, candidates, body):
        candidates = [
            item for item in candidates
            if self._recommendable(item) and self._minutes(item) <= body.available_minutes
        ]
        if not candidates:
            return []
        anchors = [
            item for item in candidates if self._sports_anchor(item, body.sport)
        ]
        if not anchors:
            return []

        def cluster(anchor):
            return [
                item
                for item in candidates
                if (distance := self._distance_km(anchor, item)) is not None
                and distance <= MAX_LEG_KM
            ]

        indexed = list(enumerate(anchors))
        _, anchor = max(
            indexed,
            key=lambda pair: (
                len(cluster(pair[1]))
                + 2
                * sum(self._theme_relevance(item, body.theme.value) for item in cluster(pair[1])),
                -pair[0],
            ),
        )
        nearby = cluster(anchor)
        nearby.sort(
            key=lambda item: (
                item.id != anchor.id,
                -self._theme_relevance(item, body.theme.value),
                self._distance_km(anchor, item) or 0,
                item.id,
            )
        )
        # Keep food/rest visible even when a district has dozens of similar sports businesses.
        if any(role(item) in {"meal", "rest"} for item in nearby):
            reserved = [anchor]
            for purpose in ("meal", "rest", "sightseeing"):
                reserved.extend([item for item in nearby if role(item) == purpose and item.id != anchor.id][:2])
            reserved_ids = {item.id for item in reserved}
            nearby = reserved + [item for item in nearby if item.id not in reserved_ids]
        nearby = nearby[:MAX_COHERENT_CANDIDATES]
        if len(nearby) <= MAX_AI_CANDIDATES:
            return nearby

        selected = [anchor]
        if any(role(item) in {"meal", "rest"} for item in nearby):
            for purpose in ("meal", "rest", "sightseeing"):
                choice = next((item for item in nearby if role(item) == purpose and item.id != anchor.id), None)
                if choice is not None:
                    selected.append(choice)
        theme_pool = [
            item
            for item in nearby
            if item not in selected and self._theme_relevance(item, body.theme.value)
        ]
        theme_target = min(
            MIN_THEME_CANDIDATES,
            len(theme_pool) + int(bool(self._theme_relevance(anchor, body.theme.value))),
        )
        while sum(bool(self._theme_relevance(item, body.theme.value)) for item in selected) < theme_target:
            weights = [1 + 2 * self._theme_relevance(item, body.theme.value) for item in theme_pool]
            choice = random.choices(theme_pool, weights=weights, k=1)[0]
            selected.append(choice)
            theme_pool.remove(choice)

        selected_ids = {item.id for item in selected}
        pool = [item for item in nearby if item.id not in selected_ids]
        while len(selected) < MAX_AI_CANDIDATES:
            weights = [1 + 2 * self._theme_relevance(item, body.theme.value) for item in pool]
            choice = random.choices(pool, weights=weights, k=1)[0]
            selected.append(choice)
            pool.remove(choice)
        selected_ids = {item.id for item in selected}
        return [item for item in nearby if item.id in selected_ids]

    def _segment(self, previous, activity) -> int | None:
        travel = 0 if previous is None else self._travel_minutes(previous, activity)
        return None if travel is None else travel + self._minutes(activity)

    def _fallback(self, candidates, body) -> list[dict]:
        if not candidates:
            return []
        starts = [item for item in candidates if self._sports_anchor(item, body.sport)]
        starts = [item for item in starts if self._minutes(item) <= body.available_minutes]
        if not starts:
            return []
        routes = []
        for main in starts:
            support = [item for item in candidates if item.id != main.id and role(item) != "activity"]
            # A later-opening experience can follow a morning visit or meal.
            prefixes = [(), *[(item,) for item in support[:3]], *permutations(support[:3], 2)]
            for prefix in prefixes:
                ordered = [*prefix, main]
                if not self._valid_roles(ordered, main.id):
                    continue
                timing = schedule(ordered, body, self._minutes, self._travel_minutes, main_id=main.id)
                if timing is None:
                    continue
                while len(ordered) < 5:
                    reachable = []
                    purposes = {stop["role"] for stop in timing}
                    for item in support:
                        proposed = [*ordered, item]
                        if item in ordered or not self._valid_roles(proposed, main.id):
                            continue
                        next_timing = schedule(proposed, body, self._minutes, self._travel_minutes, main_id=main.id)
                        if next_timing is not None:
                            reachable.append((item, next_timing))
                    if not reachable:
                        break
                    chosen, timing = min(reachable, key=lambda pair: (
                        role(pair[0]) in purposes,
                        -self._theme_relevance(pair[0], body.theme.value),
                        sum(stop["waiting_minutes"] for stop in pair[1]),
                        self._distance_km(ordered[-1], pair[0]) or 0, pair[0].id,
                    ))
                    ordered.append(chosen)
                routes.append((ordered, timing, main.id))
        if not routes:
            return []
        ordered, timing, main_id = max(routes, key=lambda route: (
            len({stop["role"] for stop in route[1]}), len(route[0]),
            -sum(stop["waiting_minutes"] for stop in route[1]),
            -sum(self._travel_minutes(a, b) or 0 for a, b in zip(route[0], route[0][1:])),
        ))
        return [{"activity_id": item.id, "reason": (
            f"{ROLE_LABELS['activity' if item.id == main_id else role(item)]}: "
            f"{item.place_name or '선택 장소'}에서의 체류와 주변 이동을 연결했습니다."
        ), "estimated_minutes": self._minutes(item)} for item in ordered]

    @staticmethod
    def _valid_roles(items, main_id):
        purposes = ["activity" if item.id == main_id else role(item) for item in items]
        return all(purposes.count(purpose) <= maximum for purpose, maximum in
                   (("activity", 1), ("meal", 1), ("rest", 1), ("sightseeing", 2)))

    def _main_id(self, selected, body):
        return next((item.id for item in selected if role(item) == "activity" and self._sports_anchor(item, body.sport)),
                    next((item.id for item in selected if self._sports_anchor(item, body.sport)), None))

    def _ai_stops(self, generated, candidates, body) -> list[dict]:
        by_id = {item.id: item for item in candidates}
        seen, total, stops, previous = set(), 0, [], None
        for stop in generated:
            item_id = int(stop["activityId"])
            if item_id not in by_id:
                raise ValueError(f"unknown candidate ID: {item_id}")
            if item_id in seen:
                raise ValueError(f"duplicate candidate ID: {item_id}")
            activity = by_id[item_id]
            minutes = self._segment(previous, activity)
            if minutes is None:
                raise ValueError(
                    f"unreachable leg: {previous.id if previous else 'start'} -> {item_id}"
                )
            if total + minutes > body.available_minutes:
                continue
            reason = str(stop["reason"]).strip()
            if not reason:
                raise ValueError(f"empty reason for candidate ID: {item_id}")
            stops.append(
                {
                    "activity_id": item_id,
                    "reason": reason,
                    "estimated_minutes": self._minutes(activity),
                }
            )
            seen.add(item_id)
            total += minutes
            previous = activity
        if not stops or not any(
            self._sports_anchor(by_id[stop["activity_id"]], body.sport) for stop in stops
        ):
            raise ValueError("AI course is empty or missing the requested sport")
        selected = [by_id[stop["activity_id"]] for stop in stops]
        main_id = self._main_id(selected, body)
        if len(selected) > 5 or not self._valid_roles(selected, main_id):
            raise ValueError("AI course repeats the main experience or supporting role")
        if schedule(selected, body, self._minutes, self._travel_minutes, main_id=main_id) is None:
            raise ValueError("AI course conflicts with travel date, operating hours or time budget")
        return stops

    def _match_score(self, stops, candidates, body) -> int:
        by_id = {activity.id: activity for activity in candidates}
        selected = [by_id[stop["activity_id"]] for stop in stops if stop["activity_id"] in by_id]
        if not selected:
            return 0
        location = sum(
            (activity.sigun == body.sigun if body.sigun else activity.region == body.region)
            for activity in selected
        ) / len(selected)
        sport = any(self._sports_anchor(item, body.sport) for item in selected)
        theme = sum(
            min(self._theme_relevance(activity, body.theme.value), 1) for activity in selected
        ) / len(selected)
        time_fit = min(
            (
                sum(stop["estimated_minutes"] for stop in stops)
                + sum(
                    self._travel_minutes(first, second) or 0
                    for first, second in zip(selected, selected[1:])
                )
            )
            / body.available_minutes,
            1,
        )
        legs = [self._distance_km(first, second) for first, second in zip(selected, selected[1:])]
        route = (
            sum(max(0, 1 - distance / MAX_LEG_KM) for distance in legs) / len(legs) if legs else 1
        )
        categories = {getattr(item.category, "value", item.category) for item in selected}
        diversity = len(categories) / min(len(selected), 3)
        return round(
            15 * location + 20 * sport + 20 * theme + 15 * time_fit + 20 * route + 10 * diversity
        )

    @staticmethod
    def _fallback_copy(body) -> tuple[str, str]:
        theme = THEME_LABELS[body.theme.value]
        area = body.sigun or body.region
        return (
            f"{area} {theme} 추천 코스",
            f"{theme} 테마에 맞춘 장소와 이동 동선을 고려한 일정입니다.",
        )

    def _result(
        self,
        stops,
        candidates,
        body,
        *,
        used_ai: bool,
        title: str | None = None,
        description: str | None = None,
    ) -> dict:
        by_id = {activity.id: activity for activity in candidates}
        selected = [by_id[stop["activity_id"]] for stop in stops]
        timing = schedule(selected, body, self._minutes, self._travel_minutes,
                          main_id=self._main_id(selected, body)) or []
        stops = [
            stop
            | {
                "place_name": activity.place_name,
                "address": getattr(activity, "address", None),
                "latitude": float(activity.latitude) if activity.latitude is not None else None,
                "longitude": float(activity.longitude) if activity.longitude is not None else None,
                "representative_image_url": getattr(activity, "representative_image_url", None),
            }
            for stop, activity in zip(stops, selected)
        ]
        legs = [
            {
                "from_activity_id": first.id,
                "to_activity_id": second.id,
                "distance_km": round(self._distance_km(first, second) or 0, 1),
                "travel_minutes": self._travel_minutes(first, second) or 0,
            }
            for first, second in zip(selected, selected[1:])
        ]
        activity_minutes = sum(stop["estimated_minutes"] for stop in stops)
        travel_minutes = sum(leg["travel_minutes"] for leg in legs)
        waiting_minutes = sum(stop["waiting_minutes"] for stop in timing)
        dated = body.travel_date is not None or "start_time" in body.model_fields_set
        if dated:
            stops = [stop | {key: value for key, value in visit.items() if key != "activity_id"}
                     for stop, visit in zip(stops, timing)]
        fallback_title, fallback_description = self._fallback_copy(body)
        result = {
            "title": title or fallback_title,
            "description": description or fallback_description,
            "activity_minutes": activity_minutes,
            "travel_minutes": travel_minutes,
            "total_estimated_minutes": activity_minutes + travel_minutes + waiting_minutes,
            "stops": stops,
            "legs": legs,
            "used_ai": used_ai,
            "match_score": self._match_score(stops, candidates, body),
        }
        if dated:
            purposes = {stop["role"] for stop in timing}
            notes = []
            if "meal" not in purposes or "rest" not in purposes:
                notes.append("현재 일정에는 식사 또는 휴식 장소가 포함되지 않았어요. 여행일이나 여유 시간을 바꿔 다른 조합도 확인해 보세요.")
            if any(stop["hours_status"] == "unknown" for stop in timing):
                notes.append("운영시간 미확인 장소가 포함되어 있어요. 출발 전 예약·휴무 여부를 확인해 주세요.")
            result |= {"travel_date": travel_day(body), "start_time": body.start_time,
                       "waiting_minutes": waiting_minutes, "planning_notes": notes}
        return result

    async def _enrich_hours(self, candidates):
        key = os.getenv("DATA_GO_KR_SERVICE_KEY")
        eligible = [item for item in candidates if getattr(item, "source", None) == "tourapi"
                    and getattr(item, "external_id", None) and not hours_info(item)["hours"]]
        if not key or not eligible:
            return
        semaphore = asyncio.Semaphore(3)
        async def fill(client, item):
            cache_key = str(item.external_id)
            cached = HOURS_CACHE.get(cache_key)
            if cached and cached[0] > time.monotonic():
                item.recommendation_hours = cached[1]
                return
            content_type = str((item.source_metadata or {}).get("contenttypeid") or "")
            if content_type not in {"12", "14", "28", "39"}:
                return
            try:
                async with semaphore:
                    response = await client.get("https://apis.data.go.kr/B551011/KorService2/detailIntro2", params={
                        "serviceKey": unquote(key), "MobileOS": "ETC", "MobileApp": "Snupel",
                        "_type": "json", "contentId": item.external_id, "contentTypeId": content_type,
                    })
                response.raise_for_status()
                rows = (response.json()["response"]["body"].get("items") or {}).get("item", [])
                details = rows[0] if isinstance(rows, list) and rows else rows if isinstance(rows, dict) else {}
                item.recommendation_hours = details
                if len(HOURS_CACHE) >= 512:
                    HOURS_CACHE.clear()
                HOURS_CACHE[cache_key] = (time.monotonic() + 3600, details)
            except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError):
                return
        try:
            async with asyncio.timeout(4):
                async with httpx.AsyncClient(timeout=3) as client:
                    await asyncio.gather(*(fill(client, item) for item in eligible))
        except TimeoutError:
            return

    async def recommend(
        self,
        body,
        *,
        require_stamp: bool = False,
        user_id: int | None = None,
    ) -> dict:
        candidates = await self.repository.recommendation_candidates(
            body.region,
            body.sigun,
            body.sport,
            body.theme.value,
            require_stamp=require_stamp,
            user_id=user_id,
        )
        candidates = self._coherent_candidates(candidates, body)
        await self._enrich_hours(candidates)
        fallback = self._fallback(candidates, body)
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logger.warning("OpenRouter recommendation fallback: API key is not configured")
            return self._result(fallback, candidates, body, used_ai=False)
        if not candidates:
            logger.warning("OpenRouter recommendation fallback: no matching candidates")
            return self._result(fallback, candidates, body, used_ai=False)
        located = next(
            (
                item
                for item in candidates
                if item.latitude is not None and item.longitude is not None
            ),
            None,
        )
        weather = None
        if located and (body.travel_date is None or body.travel_date == datetime.now(ZoneInfo("Asia/Seoul")).date()):
            try:
                async with asyncio.timeout(WEATHER_TIMEOUT_SECONDS):
                    weather = await self.weather.forecast(
                        float(located.latitude), float(located.longitude)
                    )
            except Exception:
                weather = None
        safe_candidates = [
            {
                "id": item.id,
                "title": item.place_name,
                "category": item.category.value,
                "sigun": item.sigun,
                "sport": item.sport_name,
                "summary": (item.summary or "")[:160],
                "minutes": self._minutes(item),
                "role": role(item),
                "openingHours": hours_info(item)["hours"][:400],
                "closedDays": hours_info(item)["closed"][:200],
                "travelMinutesByCandidateId": {
                    str(other.id): travel
                    for other in candidates
                    if other.id != item.id
                    and (travel := self._travel_minutes(item, other)) is not None
                },
                "matchScore": self._match_score(
                    [
                        {
                            "activity_id": item.id,
                            "estimated_minutes": self._minutes(item),
                        }
                    ],
                    candidates,
                    body,
                ),
            }
            for item in candidates
        ]
        models = list(
            dict.fromkeys(
                (
                    os.getenv("OPENROUTER_MODEL", DEFAULT_AI_MODEL),
                    os.getenv("OPENROUTER_FALLBACK_MODEL", DEFAULT_AI_FALLBACK_MODEL),
                )
            )
        )
        by_id = {item.id: item for item in candidates}
        reference_places = [by_id[stop["activity_id"]] for stop in fallback]
        reference_timing = schedule(reference_places, body, self._minutes, self._travel_minutes,
                                    main_id=self._main_id(reference_places, body)) or []
        payload = {
            "models": models,
            "max_tokens": 600,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Select an ordered, geographically coherent course using only candidate IDs. "
                        "Build a realistic day trip with ONE main sports experience, one meal, "
                        "one rest/cafe and up to two nearby sightseeing stops when available. "
                        "Never tour several competing surf schools, golf courses or rental shops. "
                        "Use feasibleReferenceRoute as a feasible baseline. If it includes meal, rest "
                        "or sightseeing, your route MUST also include those roles. "
                        "Do not invent opening hours, prices or reservation availability. "
                        "Do not maximize stop count. Respect travel date, closed days, opening windows "
                        "and breaks. Missing hours are unknown, not confirmed open. Always include "
                        "the requested sport when provided. Respect the time "
                        "limit including travel, and write a Korean course title, description, and "
                        "specific reasons. "
                        "For every consecutive pair, the next ID must exist in the previous candidate's "
                        "travelMinutesByCandidateId; add that travel time to candidate minutes."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "theme": body.theme.value,
                            "region": body.region,
                            "sigun": body.sigun,
                            "sport": body.sport,
                            "availableMinutes": body.available_minutes,
                            "travelDate": str(travel_day(body)), "startTime": body.start_time,
                            "weather": weather,
                            "candidates": safe_candidates,
                            "feasibleReferenceRoute": [{"activityId": stop["activity_id"], "role": stop["role"],
                                                        "arrivalTime": stop["arrival_time"], "departureTime": stop["departure_time"]}
                                                       for stop in reference_timing],
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "course_recommendation",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "stops": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "activityId": {"type": "integer"},
                                        "reason": {"type": "string"},
                                    },
                                    "required": ["activityId", "reason"],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["title", "description", "stops"],
                        "additionalProperties": False,
                    },
                },
            },
            "provider": {
                "data_collection": "deny",
                "require_parameters": True,
                "sort": {"by": "latency", "partition": "none"},
            },
        }
        try:
            async with asyncio.timeout(AI_TIMEOUT_SECONDS):
                async with httpx.AsyncClient(timeout=AI_TIMEOUT_SECONDS) as client:
                    response = await client.post(
                        OPENROUTER_URL,
                        headers={"Authorization": f"Bearer {api_key}"},
                        json=payload,
                    )
                    response.raise_for_status()
                    content = response.json()["choices"][0]["message"]["content"]
                    if not isinstance(content, str):
                        raise ValueError("OpenRouter returned no JSON content")
                    generated = json.loads(content)
            title = str(generated["title"]).strip()
            description = str(generated["description"]).strip()
            if not title or not description:
                raise ValueError("AI course title or description is empty")
            stops = self._ai_stops(generated["stops"], candidates, body)
            by_id = {item.id: item for item in candidates}
            fallback_places = [by_id[stop["activity_id"]] for stop in fallback]
            ai_places = [by_id[stop["activity_id"]] for stop in stops]
            def purposes(places):
                main_id = self._main_id(places, body)
                return {"activity" if item.id == main_id else role(item) for item in places}
            if not purposes(fallback_places).issubset(purposes(ai_places)):
                raise ValueError("AI course omitted a feasible meal, rest or sightseeing role")
            return self._result(
                stops, candidates, body, used_ai=True, title=title, description=description
            )
        except (
            TimeoutError,
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            logger.warning("OpenRouter recommendation fallback: %s", error, exc_info=True)
            return self._result(fallback, candidates, body, used_ai=False)

    async def generate_mission(self, body) -> dict:
        result = await self.recommend(body, require_stamp=True)
        if not result["stops"] or self.course_repository is None:
            raise ApiError(409, "mission_unavailable", "Mission could not be generated.")
        course = await self.course_repository.create_generated_mission(body, result["stops"])
        if course is None:
            raise ApiError(409, "mission_unavailable", "Mission could not be generated.")
        return result | {"course": course}


def get_recommendation_service(
    session: AsyncSession = Depends(get_session),
    weather: WeatherService = Depends(get_weather_service),
) -> RecommendationService:
    return RecommendationService(ActivityRepository(session), weather, CourseRepository(session))
