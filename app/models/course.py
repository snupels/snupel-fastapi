from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.mysql import BIGINT, INTEGER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .enums import ActivityCategory, CourseTheme


class Course(TimestampMixin, Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    category: Mapped[ActivityCategory] = mapped_column(
        SqlEnum(ActivityCategory), default=ActivityCategory.tour, server_default="tour"
    )
    sport_name: Mapped[str | None] = mapped_column(String(100))
    recommended_companion: Mapped[str | None] = mapped_column(String(100))
    representative_image_url: Mapped[str | None] = mapped_column(Text)
    estimated_duration_minutes: Mapped[int | None] = mapped_column(INTEGER(unsigned=True))
    theme: Mapped[CourseTheme] = mapped_column(SqlEnum(CourseTheme))
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    def __str__(self) -> str:
        return f"{self.title or '제목 없는 미션'} (#{self.id})"


class CourseStamp(Base):
    __tablename__ = "course_stamps"
    __table_args__ = (
        UniqueConstraint("course_id", "stamp_id", name="course_stamps_course_stamp_unique"),
        Index("course_stamps_stamp_id_idx", "stamp_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("courses.id", ondelete="CASCADE")
    )
    stamp_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("stamps.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    position: Mapped[int] = mapped_column(INTEGER(unsigned=True), default=0, server_default="0")
    course: Mapped[Course] = relationship("Course", foreign_keys=[course_id])
    stamp = relationship("Stamp", foreign_keys=[stamp_id])
