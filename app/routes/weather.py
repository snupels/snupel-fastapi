from fastapi import APIRouter, Depends, Query

from app.schemas.weather import WeatherResponse
from app.services.weather import get_weather_service

router = APIRouter(prefix="/api/weather", tags=["Weather"])


@router.get("", response_model=WeatherResponse)
async def weather(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    service=Depends(get_weather_service),
):
    return await service.forecast(latitude, longitude)
