from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SyncState(Base):
    __tablename__ = "sync_state"

    source: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_success_date: Mapped[date | None] = mapped_column(Date)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    item_count: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
