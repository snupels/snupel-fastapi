"""Register the 2026 featured Gangwon sports events."""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0003_featured_events"
down_revision = "0002_tourism_missions"
branch_labels = None
depends_on = None


EVENT_IDS = (
    "featured-2026-gangwon-trail",
    "featured-2026-pyeongchang-mtb",
    "featured-2026-inje-water",
    "featured-2026-gangneung-legacy",
)


def upgrade() -> None:
    activities = sa.table(
        "activities",
        sa.column("category", sa.String()),
        sa.column("representative_image_url", sa.Text()),
        sa.column("sport_name", sa.String()),
        sa.column("region", sa.String()),
        sa.column("sigun", sa.String()),
        sa.column("place_name", sa.String()),
        sa.column("latitude", sa.Numeric()),
        sa.column("longitude", sa.Numeric()),
        sa.column("source", sa.String()),
        sa.column("external_id", sa.String()),
        sa.column("summary", sa.Text()),
        sa.column("address", sa.String()),
        sa.column("source_url", sa.Text()),
        sa.column("starts_at", sa.DateTime()),
        sa.column("ends_at", sa.DateTime()),
        sa.column("metadata", sa.JSON()),
        sa.column("last_synced_at", sa.DateTime()),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        activities,
        [
            {
                "category": "event",
                "representative_image_url": None,
                "sport_name": None,
                "region": "강원특별자치도",
                "sigun": None,
                "place_name": "2026 강원 트레일 챌린지",
                "latitude": None,
                "longitude": None,
                "source": None,
                "external_id": EVENT_IDS[0],
                "summary": "푸른 산을 달리고, 고성봉을 오르며 강원의 자연을 온몸으로 만끽하세요.",
                "address": "강원특별자치도 산악지역 전역",
                "source_url": None,
                "starts_at": datetime(2026, 6, 3),
                "ends_at": datetime(2026, 8, 31, 23, 59, 59),
                "metadata": {"tag": "진행중"},
                "last_synced_at": None,
                "is_active": True,
            },
            {
                "category": "event",
                "representative_image_url": None,
                "sport_name": None,
                "region": "강원특별자치도",
                "sigun": "평창군",
                "place_name": "평창 MTB 익스트림 2026",
                "latitude": 37.3705,
                "longitude": 128.3903,
                "source": None,
                "external_id": EVENT_IDS[1],
                "summary": "평창의 시원한 고원과 숲길을 가르며 짜릿한 라이딩에 도전해 보세요.",
                "address": "평창군 MTB 코스 일대",
                "source_url": None,
                "starts_at": datetime(2026, 6, 20),
                "ends_at": datetime(2026, 8, 16, 23, 59, 59),
                "metadata": {"tag": "참가 모집중"},
                "last_synced_at": None,
                "is_active": True,
            },
            {
                "category": "event",
                "representative_image_url": None,
                "sport_name": None,
                "region": "강원특별자치도",
                "sigun": "인제군",
                "place_name": "인제 내린천 워터 챌린지",
                "latitude": 38.0697,
                "longitude": 128.1707,
                "source": None,
                "external_id": EVENT_IDS[2],
                "summary": "내린천의 힘찬 물살을 따라 강원의 여름을 가장 역동적으로 즐겨보세요.",
                "address": "인제군 내린천 일대",
                "source_url": None,
                "starts_at": datetime(2026, 7, 1),
                "ends_at": datetime(2026, 8, 31, 23, 59, 59),
                "metadata": {"tag": "진행중"},
                "last_synced_at": None,
                "is_active": True,
            },
            {
                "category": "event",
                "representative_image_url": None,
                "sport_name": None,
                "region": "강원특별자치도",
                "sigun": "강릉시",
                "place_name": "강릉 올림픽 레거시 투어",
                "latitude": 37.7734,
                "longitude": 128.8971,
                "source": None,
                "external_id": EVENT_IDS[3],
                "summary": "동계올림픽의 감동이 남아 있는 경기장을 걸으며 특별한 도장을 모아보세요.",
                "address": "강릉 올림픽파크 및 경기장",
                "source_url": None,
                "starts_at": datetime(2026, 6, 13),
                "ends_at": datetime(2026, 10, 31, 23, 59, 59),
                "metadata": {"tag": "참가 모집중"},
                "last_synced_at": None,
                "is_active": True,
            },
        ],
    )


def downgrade() -> None:
    activities = sa.table(
        "activities",
        sa.column("source", sa.String()),
        sa.column("external_id", sa.String()),
    )
    op.execute(
        activities.delete().where(
            activities.c.source.is_(None),
            activities.c.external_id.in_(EVENT_IDS),
        )
    )
