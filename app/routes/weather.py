from fastapi import APIRouter, Depends, Query, Request

from app.deps.rate_limit import RateLimiter
from app.exceptions import ApiError
from app.schemas.weather import WeatherResponse
from app.services.weather import get_weather_service

router = APIRouter(prefix="/api/weather", tags=["Weather"])
rate_limiter = RateLimiter(60)


@router.get("", response_model=WeatherResponse)
async def weather(
    request: Request,
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    service=Depends(get_weather_service),
):
    host = request.client.host if request.client else "local"
    if not rate_limiter.allow(host):
        raise ApiError(429, "rate_limited", "Too many requests.")
    return await service.forecast(latitude, longitude)
