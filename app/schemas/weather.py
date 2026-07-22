from datetime import datetime

from pydantic import Field

from app.schemas.common import Dto


class WeatherResponse(Dto):
    forecast_at: datetime = Field(serialization_alias="forecastAt")
    temperature_c: float | None = Field(serialization_alias="temperatureC")
    precipitation_probability: int | None = Field(serialization_alias="precipitationProbability")
    sky: str | None
    precipitation_type: str | None = Field(serialization_alias="precipitationType")
