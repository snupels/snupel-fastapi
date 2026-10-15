"""Bounded, read-only production check. Never prints credentials or user data."""
import asyncio
import json
import logging
import time

from app.config.database import SessionLocal, engine
from app.repositories.activity import ActivityRepository
from app.schemas.recommendation import CourseRecommendationRequest, CourseRecommendationResponse
from app.services.recommendation import RecommendationService
from app.services.weather import WeatherService


class SafeWarnings(logging.Handler):
    def __init__(self):
        super().__init__()
        self.reason = None

    def emit(self, record):
        if "recommendation fallback" not in record.msg:
            return
        error = record.exc_info[1] if record.exc_info else None
        if error is not None:
            response = getattr(error, "response", None)
            self.reason = {"type": type(error).__name__, "status": getattr(response, "status_code", None)}
        else:
            self.reason = {"type": "missing_key" if "API key" in record.msg else "no_candidates"}


async def main():
    handler = SafeWarnings()
    logger = logging.getLogger("app.services.recommendation")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.WARNING)
    conditions = [("양양군", "marine", 360), ("양양군", "marine", 360),
                  ("강릉시", None, 360), ("원주시", "golf", 480)]
    runs = []
    try:
        async with SessionLocal() as session:
            service = RecommendationService(ActivityRepository(session), WeatherService())
            for sigun, sport, minutes in conditions:
                body = CourseRecommendationRequest(theme="healing", region="강원특별자치도", sigun=sigun,
                                                   sport=sport, availableMinutes=minutes)
                handler.reason = None
                started = time.monotonic()
                result = await service.recommend(body)
                CourseRecommendationResponse.model_validate(result)
                roles = [s["role"] for s in result["stops"]]
                assert roles.count("activity") <= 1 and result["total_estimated_minutes"] <= minutes
                assert not {"travel_date", "start_time", "waiting_minutes"}.intersection(result)
                assert all(not {"arrival_time", "departure_time", "hours_status"}.intersection(stop) for stop in result["stops"])
                runs.append({"region": sigun, "sport": sport, "usedAi": result["used_ai"],
                             "stops": [{k: stop[k] for k in ("activity_id", "place_name", "role")} for stop in result["stops"]],
                             "minutes": result["total_estimated_minutes"], "seconds": round(time.monotonic() - started, 2), "fallback": handler.reason})
            await session.rollback()
        print(json.dumps({"runs": runs}, ensure_ascii=False))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
