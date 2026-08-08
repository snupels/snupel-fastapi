"""Link events to organizer sites and add verified sports events."""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0006_event_sources_and_sports"
down_revision = "0005_official_gangwon_events"
branch_labels = None
depends_on = None


OFFICIAL_SOURCE_URLS = {
    "gangwon-tourism-60919": "https://xn--9y5b95fmvab9w.kr/Home/H30000/festival",
    "gangwon-tourism-60917": "https://state.gwd.go.kr/portal/briefing/pressRelease?articleSeq=250440",
    "gangwon-tourism-60920": "https://www.chuncheon.go.kr/tour/guide/tour-news/?bbsId=BBSMSTR_000000000681&flag=view&nttId=1251",
    "gangwon-tourism-60752": "http://www.sunflowerfestival.co.kr/",
    "gangwon-tourism-60923": "https://ygcf.or.kr/Festival/F30000/index",
    "gangwon-tourism-60922": "https://www.hsg.go.kr/tour/contents.do?key=1375",
    "gangwon-tourism-60921": "http://www.gncn.or.kr/",
}

SPORTS_EVENTS = (
    {
        "external_id": "official-2026-go-daegwallyeong-trailrun",
        "title": "제3회 GO대관령 국제 트레일런",
        "sport_name": "트레일러닝",
        "sigun": "평창군",
        "address": "강원특별자치도 평창군 대관령면 올림픽로 220 평창동계올림픽기념공원 일원",
        "starts_at": datetime(2026, 8, 30),
        "ends_at": datetime(2026, 8, 30, 23, 59, 59),
        "image": "https://cdn.imweb.me/upload/S20240606fb90d79969e70/b5e9d0dcec56f.png",
        "source_url": "https://daegwallyeongrun.com/",
        "summary": "대관령의 산길을 달리는 44K, 20.18K, 10K 국제 트레일러닝 대회입니다.",
        "organizer": "GO대관령 국제 트레일런 조직위원회",
    },
    {
        "external_id": "official-2026-chuncheon-world-poomsae",
        "title": "춘천 2026 세계태권도품새선수권대회",
        "sport_name": "태권도",
        "sigun": "춘천시",
        "address": "강원특별자치도 춘천시 스포츠타운길 136 송암스포츠타운 에어돔",
        "starts_at": datetime(2026, 9, 16),
        "ends_at": datetime(2026, 9, 20, 23, 59, 59),
        "image": "https://cc2026wtpc.com/_user/basicFolder/img/main/main-visual-img01.jpg",
        "source_url": "https://cc2026wtpc.com/",
        "summary": "세계 각국의 선수들이 춘천에서 기량을 겨루는 세계태권도 품새 선수권대회입니다.",
        "organizer": "세계태권도연맹·춘천 레저태권도 조직위원회",
    },
    {
        "external_id": "official-2026-hongcheon-love-marathon",
        "title": "2026 홍천사랑마라톤",
        "sport_name": "마라톤",
        "sigun": "홍천군",
        "address": "강원특별자치도 홍천군 홍천읍 태학여내길 27 홍천종합운동장",
        "starts_at": datetime(2026, 10, 4, 9),
        "ends_at": datetime(2026, 10, 4, 18),
        "image": "https://www.hongcheonrun.net/assets/imgs/main_top.jpg",
        "source_url": "https://www.hongcheonrun.net/",
        "summary": "홍천종합운동장에서 출발하는 하프, 10km, 5km 마라톤 대회입니다.",
        "organizer": "홍천군체육회·홍천육상연맹",
    },
    {
        "external_id": "official-2026-chuncheon-marathon",
        "title": "2026 춘천마라톤",
        "sport_name": "마라톤",
        "sigun": "춘천시",
        "address": "강원특별자치도 춘천시 공지천교 및 의암호 순환코스",
        "starts_at": datetime(2026, 10, 25, 9),
        "ends_at": datetime(2026, 10, 25, 18),
        "image": "https://image.chosun.com/chuncheonmarathon/2026/meta-img.png",
        "source_url": "https://www.chuncheonmarathon.com/",
        "summary": "공지천교에서 출발해 의암호 국제공인코스를 달리는 풀코스 및 10km 마라톤 대회입니다.",
        "organizer": "조선일보·춘천시·스포츠조선·대한육상연맹",
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
    for external_id, source_url in OFFICIAL_SOURCE_URLS.items():
        op.execute(
            activities.update()
            .where(activities.c.external_id == external_id)
            .values(source_url=source_url)
        )

    op.bulk_insert(
        activities,
        [
            {
                "category": "event",
                "representative_image_url": event["image"],
                "sport_name": event["sport_name"],
                "region": "강원특별자치도",
                "sigun": event["sigun"],
                "place_name": event["title"],
                "latitude": None,
                "longitude": None,
                "source": None,
                "external_id": event["external_id"],
                "summary": event["summary"],
                "address": event["address"],
                "source_url": event["source_url"],
                "starts_at": event["starts_at"],
                "ends_at": event["ends_at"],
                "metadata": {
                    "officialSource": event["organizer"],
                    "eventType": "sports",
                },
                "last_synced_at": None,
                "is_active": True,
            }
            for event in SPORTS_EVENTS
        ],
    )


def downgrade() -> None:
    activities = _activities()
    sports_ids = tuple(event["external_id"] for event in SPORTS_EVENTS)
    op.execute(
        activities.delete().where(
            activities.c.source.is_(None),
            activities.c.external_id.in_(sports_ids),
        )
    )
    for external_id in OFFICIAL_SOURCE_URLS:
        article_id = external_id.removeprefix("gangwon-tourism-")
        op.execute(
            activities.update()
            .where(activities.c.external_id == external_id)
            .values(
                source_url=(
                    "https://www.gangwon.to/gwtour/now/festival"
                    f"?articleSeq={article_id}"
                )
            )
        )
