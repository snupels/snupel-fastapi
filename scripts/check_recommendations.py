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
    body = CourseRecommendationRequest(theme="healing", region="강원특별자치도", sigun="강릉시", availableMinutes=360)
    runs = []
    try:
        async with SessionLocal() as session:
            service = RecommendationService(ActivityRepository(session), WeatherService())
            for _ in range(3):
                handler.reason = None
                started = time.monotonic()
                result = await service.recommend(body)
                CourseRecommendationResponse.model_validate(result)
                runs.append({"usedAi": result["used_ai"], "ids": [s["activity_id"] for s in result["stops"]], "minutes": result["total_estimated_minutes"], "seconds": round(time.monotonic() - started, 2), "fallback": handler.reason})
            await session.rollback()
        print(json.dumps({"condition": "Gangneung/healing/360", "runs": runs, "uniqueRoutes": len({tuple(r["ids"]) for r in runs})}))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
