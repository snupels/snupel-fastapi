import os

from sqlalchemy import Index, String
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


def stamp_image_url(image_key: str) -> str:
    bucket = os.getenv("S3_BUCKET", "")
    region = os.getenv("S3_REGION", "ap-northeast-2")
    base_url = os.getenv(
        "STAMP_IMAGE_BASE_URL",
        f"https://{bucket}.s3.{region}.amazonaws.com" if bucket else "",
    ).rstrip("/")
    return f"{base_url}/{image_key}" if base_url else image_key


class StampCatalog(TimestampMixin, Base):
    __tablename__ = "stamp_catalog"
    __table_args__ = (Index("stamp_catalog_region_sport_unique", "region_en", "sport_en", unique=True),)

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    region_ko: Mapped[str] = mapped_column(String(30))
    region_en: Mapped[str] = mapped_column(String(30))
    sport_ko: Mapped[str] = mapped_column(String(30))
    sport_en: Mapped[str] = mapped_column(String(30))
    color: Mapped[str] = mapped_column(String(7))
    image_key: Mapped[str] = mapped_column(String(255))

    @property
    def image_url(self) -> str:
        return stamp_image_url(self.image_key)
