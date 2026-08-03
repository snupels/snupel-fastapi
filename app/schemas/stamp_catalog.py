from datetime import datetime

from pydantic import Field

from app.schemas.common import TimestampedResponse


class StampCatalogResponse(TimestampedResponse):
    region_ko: str = Field(serialization_alias="regionKo")
    region_en: str = Field(serialization_alias="regionEn")
    sport_ko: str = Field(serialization_alias="sportKo")
    sport_en: str = Field(serialization_alias="sportEn")
    color: str
    image_url: str = Field(serialization_alias="imageUrl")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")
