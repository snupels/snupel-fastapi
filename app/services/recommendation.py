import json
import logging
import os

import httpx
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.repositories.activity import ActivityRepository
from app.services.weather import WeatherService, get_weather_service

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
logger = logging.getLogger(__name__)


class RecommendationService:
    def __init__(self, repository: ActivityRepository, weather: WeatherService) -> None:
        self.repository = repository
        self.weather = weather

    @staticmethod
    def _minutes(activity) -> int:
        metadata = activity.source_metadata or {}
        try:
            return max(1, int(metadata.get("duration_minutes", 60)))
        except (TypeError, ValueError):
            return 60

    def _fallback(self, candidates, available_minutes: int) -> list[dict]:
        stops, used = [], 0
        for activity in candidates:
            minutes = self._minutes(activity)
            if used + minutes > available_minutes:
                continue
            stops.append(
                {
                    "activity_id": activity.id,
                    "reason": "Matches the selected region and sport.",
                    "estimated_minutes": minutes,
                }
            )
            used += minutes
        return stops

    def _match_score(self, activity_ids, candidates, body) -> int:
        by_id = {activity.id: activity for activity in candidates}
        selected = [by_id[item_id] for item_id in activity_ids if item_id in by_id]
        if not selected:
            return 0
        count = len(selected)
        region = sum(activity.region == body.region for activity in selected) / count
        sport = (
            1
            if body.sport is None
            else sum(activity.sport_name == body.sport for activity in selected) / count
        )
        theme = sum(
            bool(getattr(activity, "recommendation_theme_match", False))
            for activity in selected
        ) / count
        used_minutes = sum(self._minutes(activity) for activity in selected)
        time_fit = min(used_minutes / body.available_minutes, 1)
        return round(35 * region + 25 * sport + 25 * theme + 15 * time_fit)

    def _result(self, stops, candidates, body, *, used_ai: bool) -> dict:
        return {
            "stops": stops,
            "used_ai": used_ai,
            "match_score": self._match_score(
                [stop["activity_id"] for stop in stops], candidates, body
            ),
        }

    async def recommend(self, body) -> dict:
        candidates = await self.repository.recommendation_candidates(
            body.region, body.sport, body.theme.value
        )
        fallback = self._fallback(candidates, body.available_minutes)
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logger.warning("OpenRouter recommendation fallback: API key is not configured")
            return self._result(fallback, candidates, body, used_ai=False)
        if not candidates:
            logger.warning("OpenRouter recommendation fallback: no matching candidates")
            return self._result(fallback, candidates, body, used_ai=False)
        weather = None
        located = next((item for item in candidates if item.latitude and item.longitude), None)
        if located:
            try:
                weather = await self.weather.forecast(float(located.latitude), float(located.longitude))
            except Exception:
                weather = None
        safe_candidates = [
            {
                "id": item.id,
                "title": item.place_name,
                "category": item.category.value,
                "region": item.region,
                "sport": item.sport_name,
                "minutes": self._minutes(item),
                "matchScore": self._match_score([item.id], candidates, body),
            }
            for item in candidates
        ]
        payload = {
            "model": os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3.1"),
            "messages": [
                {
                    "role": "system",
                    "content": "Select an ordered course using only candidate IDs. Respect the time limit.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "theme": body.theme.value,
                            "region": body.region,
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
                                        "estimatedMinutes": {"type": "integer", "minimum": 1},
                                    },
                                    "required": ["activityId", "reason", "estimatedMinutes"],
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
            allowed = {item.id for item in candidates}
            seen, total, stops = set(), 0, []
            for stop in generated:
                item_id, minutes = int(stop["activityId"]), int(stop["estimatedMinutes"])
                if item_id not in allowed or item_id in seen or minutes <= 0:
                    raise ValueError
                total += minutes
                if total > body.available_minutes:
                    raise ValueError
                seen.add(item_id)
                stops.append(
                    {
                        "activity_id": item_id,
                        "reason": str(stop["reason"]),
                        "estimated_minutes": minutes,
                    }
                )
            if not stops:
                raise ValueError
            return self._result(stops, candidates, body, used_ai=True)
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            logger.warning("OpenRouter recommendation fallback: %s", error, exc_info=True)
            return self._result(fallback, candidates, body, used_ai=False)


def get_recommendation_service(
    session: AsyncSession = Depends(get_session),
    weather: WeatherService = Depends(get_weather_service),
) -> RecommendationService:
    return RecommendationService(ActivityRepository(session), weather)
