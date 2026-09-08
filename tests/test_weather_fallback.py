import asyncio
from datetime import datetime
from types import SimpleNamespace

import httpx
import pytest

from app.exceptions import ApiError
from app.services.weather import WeatherService, fallback_cache


def test_missing_kma_key_uses_cached_open_meteo(monkeypatch):
    fallback_cache.clear()
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    class Client:
        calls = 0
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            pass
        async def get(self, url, params):
            self.__class__.calls += 1
            assert url == "https://api.open-meteo.com/v1/forecast"
            assert params["timezone"] == "Asia/Seoul"
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
                "current": {"time": "2026-09-08T12:15", "temperature_2m": 23.2, "weather_code": 61},
                "hourly": {"time": ["2026-09-08T12:00"], "precipitation_probability": [70]}})
    monkeypatch.setattr("app.services.weather.httpx.AsyncClient", lambda **_: Client())
    service = WeatherService()
    first = asyncio.run(service.forecast(37.75, 128.87))
    second = asyncio.run(service.forecast(37.75, 128.87))
    assert first == second and Client.calls == 1
    assert first["source"] == "open_meteo"
    assert first["precipitation_type"] == "rain"
    assert first["precipitation_probability"] == 70
    assert first["forecast_at"].isoformat().endswith("+09:00")
    fallback_cache.clear()


def test_both_providers_unavailable_preserves_error(monkeypatch):
    fallback_cache.clear()
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            pass
        async def get(self, *_args, **_kwargs):
            raise httpx.ConnectError("offline")
    monkeypatch.setattr("app.services.weather.httpx.AsyncClient", lambda **_: Client())
    with pytest.raises(ApiError) as caught:
        asyncio.run(WeatherService().forecast(37.75, 128.87))
    assert caught.value.status == 502
    assert caught.value.code == "weather_unavailable"


def test_kma_failure_falls_back(monkeypatch):
    fallback_cache.clear()
    class Service(WeatherService):
        async def _kma_forecast(self, *_):
            raise ApiError(502, "weather_unavailable", "provider error")
        async def _open_meteo_forecast(self, *_):
            return {"source": "open_meteo", "forecast_at": datetime(2026, 9, 8)}
    assert asyncio.run(Service().forecast(37.75, 128.87))["source"] == "open_meteo"
