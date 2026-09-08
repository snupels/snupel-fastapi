from sqlalchemy import ForeignKey, UniqueConstraint, select
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, column_property, mapped_column

from .base import Base, TimestampMixin
from .user import User


class Passport(TimestampMixin, Base):
    __tablename__ = "passports"
    __table_args__ = (UniqueConstraint("user_id", name="passports_user_id_unique"),)

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    user_email: Mapped[str | None] = column_property(
        select(User.email)
        .where(User.id == user_id)
        .correlate_except(User)
        .scalar_subquery()
    )

    def __str__(self) -> str:
        return f"{self.user_email or f'사용자 #{self.user_id}'}의 패스포트 (#{self.id})"
