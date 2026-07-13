from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Passport(TimestampMixin, Base):
    __tablename__ = "passports"
    __table_args__ = (UniqueConstraint("user_id", name="passports_user_id_unique"),)

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="CASCADE")
    )
