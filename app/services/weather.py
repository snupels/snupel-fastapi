import math
import os
import time
from datetime import datetime, timedelta

import httpx

from app.exceptions import ApiError

WEATHER_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
BASE_TIMES = (2, 5, 8, 11, 14, 17, 20, 23)
SKY = {"1": "clear", "3": "cloudy", "4": "overcast"}
PTY = {"0": "none", "1": "rain", "2": "rain_snow", "3": "snow", "4": "shower"}
# ponytail: process-local cache is enough for the current single API instance; use Redis when scaling.
weather_cache: dict[tuple[int, int, str, str], tuple[float, dict]] = {}


def grid(latitude: float, longitude: float) -> tuple[int, int]:
    re, grid_size, slat1, slat2, olon, olat, xo, yo = 6371.00877, 5.0, 30.0, 60.0, 126.0, 38.0, 43.0, 136.0
    rad = math.pi / 180.0
    re /= grid_size
    slat1 *= rad
    slat2 *= rad
    olon *= rad
    olat *= rad
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(
        math.tan(math.pi * 0.25 + slat2 * 0.5)
        / math.tan(math.pi * 0.25 + slat1 * 0.5)
    )
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5) ** sn * math.cos(slat1) / sn
    ro = re * sf / math.tan(math.pi * 0.25 + olat * 0.5) ** sn
    ra = re * sf / math.tan(math.pi * 0.25 + latitude * rad * 0.5) ** sn
    theta = longitude * rad - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn
    return int(ra * math.sin(theta) + xo + 0.5), int(ro - ra * math.cos(theta) + yo + 0.5)


def base_datetime(now: datetime) -> datetime:
    available = now - timedelta(minutes=10)
    hours = [hour for hour in BASE_TIMES if hour <= available.hour]
    if hours:
        return available.replace(hour=hours[-1], minute=0, second=0, microsecond=0)
    previous = available - timedelta(days=1)
    return previous.replace(hour=23, minute=0, second=0, microsecond=0)


class WeatherService:
    async def forecast(self, latitude: float, longitude: float, now: datetime | None = None) -> dict:
        key = os.getenv("DATA_GO_KR_SERVICE_KEY")
        if not key:
            raise ApiError(503, "weather_unavailable", "Public data service key is not configured.")
        current = now or datetime.now()
        base = base_datetime(current)
        nx, ny = grid(latitude, longitude)
        cache_key = (nx, ny, base.strftime("%Y%m%d"), base.strftime("%H%M"))
        cached = weather_cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        params = {
            "serviceKey": key,
            "pageNo": 1,
            "numOfRows": 1000,
            "dataType": "JSON",
            "base_date": cache_key[2],
            "base_time": cache_key[3],
            "nx": nx,
            "ny": ny,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(WEATHER_URL, params=params)
                response.raise_for_status()
                items = response.json()["response"]["body"]["items"]["item"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ApiError(502, "weather_unavailable", "Weather provider request failed.") from error
        forecasts: dict[tuple[str, str], dict[str, str]] = {}
        for item in items:
            forecasts.setdefault((item["fcstDate"], item["fcstTime"]), {})[
                item["category"]
            ] = item["fcstValue"]
        future = [slot for slot in sorted(forecasts) if datetime.strptime("".join(slot), "%Y%m%d%H%M") >= current]
        if not future:
            raise ApiError(502, "weather_unavailable", "Weather provider returned no forecast.")
        slot = future[0]
        values = forecasts[slot]
        result = {
            "forecast_at": datetime.strptime("".join(slot), "%Y%m%d%H%M"),
            "temperature_c": float(values["TMP"]) if "TMP" in values else None,
            "precipitation_probability": int(values["POP"]) if "POP" in values else None,
            "sky": SKY.get(values.get("SKY")),
            "precipitation_type": PTY.get(values.get("PTY")),
        }
        weather_cache[cache_key] = (time.monotonic() + 1800, result)
        return result


def get_weather_service() -> WeatherService:
    return WeatherService()
