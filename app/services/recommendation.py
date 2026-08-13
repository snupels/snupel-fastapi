import json
import logging
import math
import os

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
MAX_AI_CANDIDATES = 15
CATEGORY_MINUTES = {"tour": 45, "sports": 90, "event": 60}
THEME_LABELS = {
    "healing": "힐링",
    "thrill": "스릴",
    "photo_spot": "포토스팟",
    "stamp": "스탬프",
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
            return 6371 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))
        if first.sigun and first.sigun == second.sigun:
            return 10
        return None

    def _travel_minutes(self, first, second) -> int | None:
        distance = self._distance_km(first, second)
        if distance is None or distance > MAX_LEG_KM:
            return None
        return 0 if not distance else max(10, math.ceil(distance / AVERAGE_KPH * 60))

    def _coherent_candidates(self, candidates, body):
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
                * sum(
                    bool(getattr(item, "recommendation_theme_match", False))
                    for item in cluster(pair[1])
                ),
                -pair[0],
            ),
        )
        nearby = cluster(anchor)
        nearby.sort(
            key=lambda item: (
                item.id != anchor.id,
                not bool(getattr(item, "recommendation_theme_match", False)),
                self._distance_km(anchor, item) or 0,
                item.id,
            )
        )
        return nearby[:MAX_AI_CANDIDATES]

    def _segment(self, previous, activity) -> int | None:
        travel = 0 if previous is None else self._travel_minutes(previous, activity)
        return None if travel is None else travel + self._minutes(activity)

    def _fallback(self, candidates, body) -> list[dict]:
        if not candidates:
            return []
        remaining = list(candidates)
        first = next(
            (item for item in remaining if body.sport and item.sport_name == body.sport),
            remaining[0],
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
                    not bool(getattr(item, "recommendation_theme_match", False)),
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
            bool(getattr(activity, "recommendation_theme_match", False)) for activity in selected
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

    async def recommend(self, body, *, require_stamp: bool = False) -> dict:
        candidates = await self.repository.recommendation_candidates(
            body.region,
            body.sigun,
            body.sport,
            body.theme.value,
            require_stamp=require_stamp,
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
                "summary": (item.summary or "")[:300],
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
        payload = {
            "model": os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3.1"),
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
            "provider": {"data_collection": "deny", "require_parameters": True},
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    OPENROUTER_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                generated = json.loads(response.json()["choices"][0]["message"]["content"])["stops"]
            stops = self._ai_stops(generated, candidates, body)
            return self._result(stops, candidates, body, used_ai=True)
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
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
