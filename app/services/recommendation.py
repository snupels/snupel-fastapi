import asyncio
import json
import logging
import math
import os
import random

import httpx
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.exceptions import ApiError
from app.repositories.activity import ActivityRepository
from app.repositories.course import CourseRepository
from app.services.weather import WeatherService, get_weather_service

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_LEG_KM = 40
AVERAGE_KPH = 40
ROAD_DISTANCE_FACTOR = 1.3
MAX_COHERENT_CANDIDATES = 30
MAX_AI_CANDIDATES = 10
WEATHER_TIMEOUT_SECONDS = 2
AI_TIMEOUT_SECONDS = 12
DEFAULT_AI_MODEL = "deepseek/deepseek-chat-v3.1"
DEFAULT_AI_FALLBACK_MODEL = "deepseek/deepseek-v3.1-terminus"
CATEGORY_MINUTES = {"tour": 45, "sports": 90, "event": 60}
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
            return max(1, int(metadata.get("duration_minutes", CATEGORY_MINUTES[category])))
        except (KeyError, TypeError, ValueError):
            return 60

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
            return straight_line_km * ROAD_DISTANCE_FACTOR
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
        return content_type != "32" and not (
            content_type == "15"
            and getattr(activity, "starts_at", None) is None
            and getattr(activity, "ends_at", None) is None
        )

    def _coherent_candidates(self, candidates, body):
        candidates = [item for item in candidates if self._recommendable(item)]
        if not candidates:
            return []
        anchors = [
            item for item in candidates if body.sport is None or item.sport_name == body.sport
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
        nearby = nearby[:MAX_COHERENT_CANDIDATES]
        if len(nearby) <= MAX_AI_CANDIDATES:
            return nearby

        selected = [anchor] if body.sport else []
        pool = [item for item in nearby if item.id != anchor.id or not body.sport]
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
        relevant = [item for item in candidates if self._theme_relevance(item, body.theme.value)]
        remaining = list(candidates) if body.sport else relevant or list(candidates)
        first = next(
            (item for item in remaining if body.sport and item.sport_name == body.sport),
            max(
                remaining,
                key=lambda item: self._theme_relevance(item, body.theme.value),
            ),
        )
        ordered, previous = [first], first
        remaining.remove(first)
        while remaining:
            reachable = [
                item for item in remaining if self._travel_minutes(previous, item) is not None
            ]
            if not reachable:
                break
            previous = min(
                reachable,
                key=lambda item: (
                    -self._theme_relevance(item, body.theme.value),
                    self._distance_km(previous, item) or 0,
                    item.id,
                ),
            )
            ordered.append(previous)
            remaining.remove(previous)

        stops, total, previous = [], 0, None
        theme = THEME_LABELS[body.theme.value]
        for activity in ordered:
            minutes = self._segment(previous, activity)
            if minutes is None or total + minutes > body.available_minutes:
                continue
            stops.append(
                {
                    "activity_id": activity.id,
                    "reason": (
                        f"{activity.place_name or '선택 장소'}: "
                        f"{theme} 테마와 가까운 이동 동선을 고려했습니다."
                    ),
                    "estimated_minutes": minutes,
                }
            )
            total += minutes
            previous = activity
        return stops

    def _ai_stops(self, generated, candidates, body) -> list[dict]:
        by_id = {item.id: item for item in candidates}
        seen, total, stops, previous = set(), 0, [], None
        for stop in generated:
            item_id = int(stop["activityId"])
            if item_id not in by_id or item_id in seen:
                raise ValueError
            activity = by_id[item_id]
            minutes = self._segment(previous, activity)
            if minutes is None:
                raise ValueError
            if total + minutes > body.available_minutes:
                continue
            reason = str(stop["reason"]).strip()
            if not reason:
                raise ValueError
            stops.append(
                {
                    "activity_id": item_id,
                    "reason": reason,
                    "estimated_minutes": minutes,
                }
            )
            seen.add(item_id)
            total += minutes
            previous = activity
        if not stops or (
            body.sport
            and not any(by_id[stop["activity_id"]].sport_name == body.sport for stop in stops)
        ):
            raise ValueError
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
        sport = 1 if body.sport is None else any(item.sport_name == body.sport for item in selected)
        theme = sum(
            min(self._theme_relevance(activity, body.theme.value), 1) for activity in selected
        ) / len(selected)
        time_fit = min(
            sum(stop["estimated_minutes"] for stop in stops) / body.available_minutes,
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

    def _result(self, stops, candidates, body, *, used_ai: bool) -> dict:
        return {
            "stops": stops,
            "used_ai": used_ai,
            "match_score": self._match_score(stops, candidates, body),
        }

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
        if located:
            try:
                async with asyncio.timeout(WEATHER_TIMEOUT_SECONDS):
                    weather = await self.weather.forecast(
                        float(located.latitude), float(located.longitude)
                    )
            except Exception:
                weather = None
        anchor = candidates[0]
        safe_candidates = [
            {
                "id": item.id,
                "title": item.place_name,
                "category": item.category.value,
                "sigun": item.sigun,
                "sport": item.sport_name,
                "summary": (item.summary or "")[:160],
                "minutes": self._minutes(item),
                "distanceFromAnchorKm": round(self._distance_km(anchor, item) or 0, 1),
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
        payload = {
            "models": models,
            "max_tokens": 600,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Select an ordered, geographically coherent course using only candidate IDs. "
                        "Choose up to five varied stops, include the requested sport when provided, "
                        "respect the time limit including travel, and write specific reasons in Korean."
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
                            "weather": weather,
                            "candidates": safe_candidates,
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
                        "required": ["stops"],
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
                    generated = json.loads(content)["stops"]
            stops = self._ai_stops(generated, candidates, body)
            return self._result(stops, candidates, body, used_ai=True)
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
