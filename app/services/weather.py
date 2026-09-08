import math
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import httpx

from app.exceptions import ApiError

WEATHER_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
BASE_TIMES = (2, 5, 8, 11, 14, 17, 20, 23)
SKY = {"1": "clear", "3": "cloudy", "4": "overcast"}
PTY = {"0": "none", "1": "rain", "2": "rain_snow", "3": "snow", "4": "shower"}
# ponytail: process-local cache is enough for the current single API instance; use Redis when scaling.
weather_cache: dict[tuple[int, int, str, str], tuple[float, dict]] = {}
fallback_cache: dict[tuple[float, float], tuple[float, dict]] = {}
KST = timezone(timedelta(hours=9))


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
        coordinates = (round(latitude, 3), round(longitude, 3))
        cached = fallback_cache.get(coordinates)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        try:
            return await self._kma_forecast(latitude, longitude, now)
        except ApiError:
            # Keep the same public response contract if the KMA service is unavailable.
            return await self._open_meteo_forecast(*coordinates)

    async def _open_meteo_forecast(self, latitude: float, longitude: float) -> dict:
        params = {"latitude": latitude, "longitude": longitude,
                  "current": "temperature_2m,weather_code",
                  "hourly": "precipitation_probability", "forecast_days": 1,
                  "timezone": "Asia/Seoul"}
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
                response.raise_for_status()
                data = response.json()
            current = data["current"]
            forecast_at = datetime.fromisoformat(current["time"]).replace(tzinfo=KST)
            code = int(current["weather_code"])
            temperature = float(current["temperature_2m"])
            if not math.isfinite(temperature):
                raise ValueError("Invalid temperature")
            hourly = data.get("hourly", {})
            hour = forecast_at.strftime("%Y-%m-%dT%H:00")
            times = hourly.get("time", [])
            probability = hourly.get("precipitation_probability", [])[times.index(hour)] if hour in times else None
            result = {
                "forecast_at": forecast_at, "temperature_c": temperature,
                "precipitation_probability": int(probability) if probability is not None else None,
                "sky": "clear" if code in (0, 1) else "cloudy" if code == 2 else "overcast",
                "precipitation_type": "snow" if code in (71, 73, 75, 77, 85, 86) else "rain" if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99) else "none",
                "source": "open_meteo",
            }
        except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError) as error:
            raise ApiError(502, "weather_unavailable", "Weather providers are temporarily unavailable.") from error
        if len(fallback_cache) >= 512:
            fallback_cache.clear()
        fallback_cache[(latitude, longitude)] = (time.monotonic() + 900, result)
        return result

    async def _kma_forecast(self, latitude: float, longitude: float, now: datetime | None = None) -> dict:
        key = os.getenv("DATA_GO_KR_SERVICE_KEY")
        if not key:
            raise ApiError(503, "weather_unavailable", "Public data service key is not configured.")
        current = now or datetime.now(KST).replace(tzinfo=None)
        if current.tzinfo is not None:
            current = current.astimezone(KST).replace(tzinfo=None)
        base = base_datetime(current)
        nx, ny = grid(latitude, longitude)
        cache_key = (nx, ny, base.strftime("%Y%m%d"), base.strftime("%H%M"))
        cached = weather_cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        params = {
            "serviceKey": unquote(key),
            "pageNo": 1,
            "numOfRows": 1000,
            "dataType": "JSON",
            "base_date": cache_key[2],
            "base_time": cache_key[3],
            "nx": nx,
            "ny": ny,
        }
        try:
            async with httpx.AsyncClient(timeout=5) as client:
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
            "source": "kma",
        }
        weather_cache[cache_key] = (time.monotonic() + 1800, result)
        return result


def get_weather_service() -> WeatherService:
    return WeatherService()
