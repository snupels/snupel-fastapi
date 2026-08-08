"""Replace placeholder events with verified Gangwon tourism events."""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0005_official_gangwon_events"
down_revision = "0004_featured_events"
branch_labels = None
depends_on = None


PLACEHOLDER_EVENT_IDS = (
    "featured-2026-gangwon-trail",
    "featured-2026-pyeongchang-mtb",
    "featured-2026-inje-water",
    "featured-2026-gangneung-legacy",
)

OFFICIAL_EVENTS = (
    {
        "article_id": "60919",
        "title": "제10회 홍천강 별빛음악 맥주축제",
        "sigun": "홍천군",
        "address": "강원특별자치도 홍천군 홍천읍 갈마곡리 501 도시산림공원 토리숲",
        "starts_at": datetime(2026, 8, 5),
        "ends_at": datetime(2026, 8, 9, 23, 59, 59),
        "image": "https://www.gangwon.to/upload/board/BDMAIN02/e72f8eb2-a69b-4098-8367-a247fbf05ec2.png",
        "summary": "맥주와 음악, 공연 및 체험 프로그램을 함께 즐기는 홍천의 여름 축제입니다.",
    },
    {
        "article_id": "60917",
        "title": "나라꽃 무궁화 전시회",
        "sigun": "춘천시",
        "address": "강원특별자치도 춘천시 화목원길 24",
        "starts_at": datetime(2026, 8, 1),
        "ends_at": datetime(2026, 8, 17, 23, 59, 59),
        "image": "https://www.gangwon.to/upload/board/BDMAIN02/c272726d-1141-40b8-af50-e60719f18d69.png",
        "summary": "강원도립화목원에서 나라꽃 무궁화를 만나는 전시 행사입니다.",
    },
    {
        "article_id": "60920",
        "title": "춘천 썸머워터 페스티벌",
        "sigun": "춘천시",
        "address": "강원특별자치도 춘천시 삼천동 200-9 춘천수변공원",
        "starts_at": datetime(2026, 7, 17),
        "ends_at": datetime(2026, 8, 17, 23, 59, 59),
        "image": "https://www.gangwon.to/upload/board/BDMAIN02/f038b0da-a23f-4064-bab3-586414ea18da.png",
        "summary": "춘천수변공원에서 다양한 풀과 워터 슬라이드를 즐기는 여름 물놀이 축제입니다.",
    },
    {
        "article_id": "60752",
        "title": "태백 해바라기축제",
        "sigun": "태백시",
        "address": "강원특별자치도 태백시 구와우길 38-20 태백해바라기축제장",
        "starts_at": datetime(2026, 7, 17),
        "ends_at": datetime(2026, 8, 17, 23, 59, 59),
        "image": "https://www.gangwon.to/upload/board/BDMAIN02/f35e67e4-004e-473f-bc40-6bcc35f5bd12.jpg",
        "summary": "구와우마을의 해바라기 평원과 코스모스 언덕, 야외 작품을 함께 즐기는 축제입니다.",
    },
    {
        "article_id": "60923",
        "title": "국토정중앙 청춘양구 배꼽축제",
        "sigun": "양구군",
        "address": "강원특별자치도 양구군 양구읍 상리 394-21",
        "starts_at": datetime(2026, 8, 28),
        "ends_at": datetime(2026, 8, 30, 23, 59, 59),
        "image": "https://www.gangwon.to/upload/board/BDMAIN02/7e10abab-5265-4bc2-8e1e-1f505a80ddac.png",
        "summary": "국토 정중앙 양구에서 열리는 여름 지역 축제입니다.",
    },
    {
        "article_id": "60922",
        "title": "둔내고랭지토마토축제",
        "sigun": "횡성군",
        "address": "강원특별자치도 횡성군 둔내면 경강로 4708",
        "starts_at": datetime(2026, 8, 14),
        "ends_at": datetime(2026, 8, 16, 23, 59, 59),
        "image": "https://www.gangwon.to/upload/board/BDMAIN02/6e5b2d27-f245-4a9e-be5a-a11790d49dc1.png",
        "summary": "둔내 고랭지 토마토를 주제로 열리는 횡성의 지역 축제입니다.",
    },
    {
        "article_id": "60921",
        "title": "강릉 국가유산 야행",
        "sigun": "강릉시",
        "address": "강원특별자치도 강릉시 임영로131번길 6 임영관",
        "starts_at": datetime(2026, 8, 14),
        "ends_at": datetime(2026, 8, 16, 23, 59, 59),
        "image": "https://www.gangwon.to/upload/board/BDMAIN02/1e184a87-8e1c-4fcf-9ea6-db4b975d9675.png",
        "summary": "강릉의 국가유산을 밤에 둘러보며 공연과 체험을 즐기는 문화 행사입니다.",
    },
)


def _activities():
    return sa.table(
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


def upgrade() -> None:
    activities = _activities()
    op.execute(
        activities.delete().where(
            activities.c.source.is_(None),
            activities.c.external_id.in_(PLACEHOLDER_EVENT_IDS),
        )
    )
    op.bulk_insert(
        activities,
        [
            {
                "category": "event",
                "representative_image_url": event["image"],
                "sport_name": None,
                "region": "강원특별자치도",
                "sigun": event["sigun"],
                "place_name": event["title"],
                "latitude": None,
                "longitude": None,
                "source": None,
                "external_id": f"gangwon-tourism-{event['article_id']}",
                "summary": event["summary"],
                "address": event["address"],
                "source_url": f"https://www.gangwon.to/gwtour/now/festival?articleSeq={event['article_id']}",
                "starts_at": event["starts_at"],
                "ends_at": event["ends_at"],
                "metadata": {
                    "officialSource": "강원관광",
                    "articleSeq": event["article_id"],
                },
                "last_synced_at": None,
                "is_active": True,
            }
            for event in OFFICIAL_EVENTS
        ],
    )


def downgrade() -> None:
    activities = _activities()
    official_ids = tuple(
        f"gangwon-tourism-{event['article_id']}" for event in OFFICIAL_EVENTS
    )
    op.execute(
        activities.delete().where(
            activities.c.source.is_(None),
            activities.c.external_id.in_(official_ids),
        )
    )
