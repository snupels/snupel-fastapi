from datetime import datetime
from enum import Enum

from pydantic import Field

from app.schemas.common import Dto


class StampbookFilter(str, Enum):
    all = "all"
    collected = "collected"
    available = "available"
    locked = "locked"


class StampbookStatus(str, Enum):
    collected = "collected"
    available = "available"
    locked = "locked"


class StampbookSummary(Dto):
    total: int = Field(ge=0)
    collected: int = Field(ge=0)
    available: int = Field(ge=0)
    locked: int = Field(ge=0)


class StampbookCourse(Dto):
    id: int = Field(gt=0)
    title: str | None


class StampbookItem(Dto):
    catalog_id: int = Field(gt=0, serialization_alias="catalogId")
    stamp_id: int | None = Field(serialization_alias="stampId")
    region_ko: str = Field(serialization_alias="regionKo")
    region_en: str = Field(serialization_alias="regionEn")
    sport_ko: str = Field(serialization_alias="sportKo")
    sport_en: str = Field(serialization_alias="sportEn")
    color: str
    image_url: str = Field(serialization_alias="imageUrl")
    status: StampbookStatus
    collected_at: datetime | None = Field(serialization_alias="collectedAt")
    courses: list[StampbookCourse]


class StampbookResponse(Dto):
    summary: StampbookSummary
    page: int = Field(ge=1)
    size: int = Field(ge=1, le=100)
    total_items: int = Field(ge=0, serialization_alias="totalItems")
    total_pages: int = Field(ge=0, serialization_alias="totalPages")
    items: list[StampbookItem]
