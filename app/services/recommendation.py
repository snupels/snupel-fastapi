import json
import os

import httpx
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_session
from app.repositories.activity import ActivityRepository
from app.services.weather import WeatherService, get_weather_service

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


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

    async def recommend(self, body) -> dict:
        candidates = await self.repository.recommendation_candidates(
            body.region, body.sport, body.theme.value
        )
        fallback = self._fallback(candidates, body.available_minutes)
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key or not candidates:
            return {"stops": fallback, "used_ai": False}
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
            return {"stops": stops, "used_ai": True}
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return {"stops": fallback, "used_ai": False}


def get_recommendation_service(
    session: AsyncSession = Depends(get_session),
    weather: WeatherService = Depends(get_weather_service),
) -> RecommendationService:
    return RecommendationService(ActivityRepository(session), weather)
