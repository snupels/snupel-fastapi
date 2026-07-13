from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Date,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT, INTEGER
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Gender(str, Enum):
    male = "male"
    female = "female"
    other = "other"
    unknown = "unknown"


class ActivityCategory(str, Enum):
    sports = "sports"
    event = "event"
    festival = "festival"


class CourseTheme(str, Enum):
    healing = "healing"
    thrill = "thrill"
    photo_spot = "photo_spot"
    stamp = "stamp"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="users_email_unique"),)

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(Text)
    birth_date: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[Gender | None] = mapped_column(SqlEnum(Gender))


class SocialAccount(TimestampMixin, Base):
    __tablename__ = "social_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="social_accounts_provider_user_unique"),
        Index("social_accounts_user_id_idx", "user_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(50))
    provider_user_id: Mapped[str] = mapped_column(String(255))


class Passport(TimestampMixin, Base):
    __tablename__ = "passports"
    __table_args__ = (UniqueConstraint("user_id", name="passports_user_id_unique"),)

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("users.id", ondelete="CASCADE"))


class Activity(TimestampMixin, Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    category: Mapped[ActivityCategory] = mapped_column(SqlEnum(ActivityCategory))
    representative_image_url: Mapped[str | None] = mapped_column(Text)
    sport_name: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    place_name: Mapped[str | None] = mapped_column(String(255))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))


class Stamp(TimestampMixin, Base):
    __tablename__ = "stamps"
    __table_args__ = (Index("stamps_activity_id_idx", "activity_id"),)

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("activities.id", ondelete="CASCADE"))
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)


class CollectedStamp(Base):
    __tablename__ = "collected_stamps"
    __table_args__ = (
        UniqueConstraint("passport_id", "stamp_id", name="collected_stamps_passport_stamp_unique"),
        Index("collected_stamps_stamp_id_idx", "stamp_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    passport_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("passports.id", ondelete="CASCADE"))
    stamp_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("stamps.id", ondelete="CASCADE"))
    collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class Badge(TimestampMixin, Base):
    __tablename__ = "badges"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    image_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)


class CollectedBadge(Base):
    __tablename__ = "collected_badges"
    __table_args__ = (
        UniqueConstraint("passport_id", "badge_id", name="collected_badges_passport_badge_unique"),
        Index("collected_badges_badge_id_idx", "badge_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    passport_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("passports.id", ondelete="CASCADE"))
    badge_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("badges.id", ondelete="CASCADE"))
    collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class Course(TimestampMixin, Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    recommended_companion: Mapped[str | None] = mapped_column(String(100))
    representative_image_url: Mapped[str | None] = mapped_column(Text)
    estimated_duration_minutes: Mapped[int | None] = mapped_column(INTEGER(unsigned=True))
    theme: Mapped[CourseTheme] = mapped_column(SqlEnum(CourseTheme))


class CourseStamp(Base):
    __tablename__ = "course_stamps"
    __table_args__ = (
        UniqueConstraint("course_id", "stamp_id", name="course_stamps_course_stamp_unique"),
        Index("course_stamps_stamp_id_idx", "stamp_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("courses.id", ondelete="CASCADE"))
    stamp_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("stamps.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
