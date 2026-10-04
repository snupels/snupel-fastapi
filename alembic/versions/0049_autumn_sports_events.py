"""Add four publicly accessible Gangwon sports events verified on 2026-10-04.

Official organizer curation is separate from TourAPI source records. Where only
a deadline date is published, end-of-day KST is a display-status cutoff, not a
promise of availability until that time. Exact times are omitted from the guide.
"""
from datetime import datetime, timedelta

from alembic import op
import sqlalchemy as sa

revision = "0049_autumn_sports_events"
down_revision = "0048_tourism_sync_state"
branch_labels = None
depends_on = None

PUBLIC_EVENTS = (
    {
        "external_id": "official-2026-wonju-baramgil-donation-run",
        "place_name": "2026 원주 바람길숲 기부런",
        "sport_name": "러닝", "sigun": "원주시",
        "address": "강원특별자치도 원주시 반곡동 1902, 혁신페스타 행사장 및 치악산 바람길숲",
        "starts_at": datetime(2026, 10, 17, 8),
        "ends_at": datetime(2026, 10, 17, 13, 30),
        "source_url": "https://cltoo.com/ko/product/379?category=CL_TO_EDITION",
        "representative_image_url": "https://tripboard.kr.object.ncloudstorage.com/PRODUCT/379/tour/%E1%84%83%E1%85%A2%E1%84%92%E1%85%AC%20Hero%20-%201360_590-taw2f6.png",
        "summary": "원주 혁신페스타와 치악산 바람길숲을 잇는 10km 기부 러닝 행사입니다. 기록 경쟁 없이 자신의 페이스에 맞춰 달리며, 참가비 전액을 기부합니다.",
        "metadata": {
            "eventType": "sports", "curationSource": "official_organizer",
            "officialSource": "한국관광공사·강원혁신도시발전지원센터 / 클투 공식 접수",
            "imageType": "poster", "imageCaption": "2026 원주 바람길숲 기부런 공식 행사 이미지",
            "participation": {
                "mode": "registration", "status": "open", "verifiedAt": "2026-10-04",
                "firstCome": True, "onsiteAvailable": False,
                "closesAt": "2026-10-13T23:59:59+09:00",
                "programs": "10km 비경쟁 러닝 · 페이스별 그룹 선택",
                "eligibility": "12세 이상, 기부 러닝에 참여하고 싶은 누구나",
                "fee": "30,000원(전액 기부)",
                "registrationGuide": "클투 회원가입 후 온라인 신청. 9월 23일~10월 13일 모집하며, 결제 완료 기준 500명 선착순 마감입니다.",
                "note": "기록칩과 공식 기록 측정은 없습니다. 등록 데스크는 원주 혁신도시 미리내거리(반곡동 1902)입니다. 취소·환불은 10월 12일 23:59까지이며, 잔여석은 접수처에서 확인해 주세요.",
                "evidenceUrls": ["https://cltoo.com/ko/product/379?category=CL_TO_EDITION"],
            },
        },
    },
    {
        "external_id": "official-2026-tour-5k-mangsang",
        "place_name": "TOUR 5K 망상 & TOUR 비치 플로깅 망상",
        "sport_name": "러닝", "sigun": "동해시",
        "address": "강원특별자치도 동해시 동해대로 6270-23, 망상해수욕장",
        "starts_at": datetime(2026, 10, 24, 8),
        "ends_at": datetime(2026, 10, 24, 11),
        "source_url": "https://mypb.info/competition/666",
        "representative_image_url": "https://cdn.mypb.info/public/image/2026/09/3379593a-8ee5-4af1-97f9-26509f27849d.webp",
        "summary": "망상해수욕장에서 열리는 5km 러닝과 해변 플로깅 행사입니다. 동해 바다를 배경으로 달리거나 해변 환경 정화 활동에 참여할 수 있습니다.",
        "metadata": {
            "eventType": "sports", "curationSource": "official_organizer",
            "officialSource": "SPONOVATION / myPB 공식 접수",
            "imageType": "poster", "imageCaption": "TOUR 5K 망상 공식 행사 이미지",
            "participation": {
                "mode": "registration", "status": "open", "verifiedAt": "2026-10-04",
                "opensAt": "2026-09-11T12:00:00+09:00",
                "closesAt": "2026-10-17T23:59:00+09:00",
                "programs": "TOUR 5K 망상 · TOUR 비치 플로깅",
                "fee": "5km 러닝 30,000원. 플로깅 참가비·조건은 종목 선택 후 확인해 주세요.",
                "registrationGuide": "myPB 공식 접수 페이지에서 종목을 선택해 신청합니다. 접수는 10월 17일 23:59까지이며, 5km 종목 정원은 1,000명입니다.",
                "note": "공식 환불 규정상 10월 1일부터 환불이 불가합니다. 신청 전 참가 조건과 취소 규정을 확인해 주세요.",
                "evidenceUrls": ["https://mypb.info/competition/666"],
            },
        },
    },
    {
        "external_id": "official-2026-buldak-burning-festa",
        "place_name": "불닭 버닝 페스타 With 페포",
        "sport_name": "트레일러닝", "sigun": "평창군",
        "address": "강원특별자치도 평창군 삼양라운드힐",
        "starts_at": datetime(2026, 10, 24, 9),
        "ends_at": datetime(2026, 10, 25, 10, 30),
        "source_url": "https://sqnc.global/buldak-burning-festa-with-peppo",
        "representative_image_url": "https://cdn.buldak.com/images/1789697180139-01news_pc_800_1200_c_20260918110619.png?fit=cover&q=80&w=1440",
        "summary": "평창 삼양라운드힐에서 트레일러닝과 캠핑·웰니스를 함께 즐기는 이틀간의 행사입니다. 러닝은 10월 24일 진행되며, 5km부터 23km까지 자신의 경험에 맞는 코스를 선택할 수 있습니다.",
        "metadata": {
            "eventType": "sports", "curationSource": "official_organizer",
            "officialSource": "삼양식품·프렌트립",
            "imageType": "poster", "imageCaption": "불닭 버닝 페스타 With 페포 공식 홍보 이미지",
            "participation": {
                "mode": "registration", "status": "open", "verifiedAt": "2026-10-04",
                "closesAt": "2026-10-05T23:59:59+09:00",
                "programs": "23K(11:00) · 5K(11:30) · 13K(12:00), 러닝 종료 제한 15:30",
                "eligibility": "만 19세 이상. 5K는 보호자 동반 미성년자도 별도 상품으로 신청 가능",
                "fee": "23K 90,000원 / 13K 70,000원 / 5K 성인 50,000원·미성년자 30,000원. 리커버리 패키지는 별도 신청",
                "registrationGuide": "공식 예약 사이트에서 10월 5일까지 접수합니다. 코스별 정원 도달 시 조기 마감될 수 있으므로 잔여석을 확인해 주세요.",
                "note": "최신 공식 공지에서 5K 출발 지점·코스와 피니시 지점이 변경되었습니다. 참가 전 변경 코스와 필수 장비를 확인해 주세요. 다음 날 웰니스 프로그램 예약은 별도 안내됩니다.",
                "evidenceUrls": [
                    "https://sqnc.global/buldak-burning-festa-with-peppo",
                    "https://buldak.com/kr/news/kr-buldak-burning-festa-peppo/",
                ],
            },
        },
    },
    {
        "external_id": "official-2026-marvel-run-inje",
        "place_name": "마블런 2026 인제",
        "sport_name": "러닝", "sigun": "인제군",
        "address": "강원특별자치도 인제군 기린면 상하답로 130, 인제스피디움",
        "starts_at": datetime(2026, 10, 31, 11),
        "ends_at": datetime(2026, 10, 31, 19),
        "source_url": "https://marvelrunkorea2026.com/",
        "representative_image_url": "https://marvelrunkorea2026.com/images/main/hero-characters.png",
        "summary": "인제스피디움 서킷을 달리는 마블 테마 러닝 행사입니다. 10km·5km와 가족 단위로 참여할 수 있는 2.3km 코스를 운영하며, 러닝 후 무대 행사가 이어집니다.",
        "metadata": {
            "eventType": "sports", "curationSource": "official_organizer",
            "officialSource": "마블런 2026 운영사무국",
            "imageType": "poster", "imageCaption": "마블런 2026 공식 행사 이미지 · ©2026 MARVEL",
            "participation": {
                "mode": "registration", "status": "open", "verifiedAt": "2026-10-04",
                "opensAt": "2026-09-22T14:00:00+09:00",
                "programs": "10km 13:30 · 5km 14:00 · 2.3km 패밀리 코스 14:30 출발",
                "eligibility": "10km는 만 12세 이하 참가 불가. 어린이는 5km·2.3km 참가 조건을 확인해 주세요.",
                "fee": "10km·5km 성인 70,000원 / 2.3km 성인 55,000원 / 5km·2.3km 어린이 40,000원",
                "registrationGuide": "공식 홈페이지의 참가신청에서 코스를 선택합니다. 9월 22일 14:00 접수 개시. 마감일과 잔여석은 공식 접수 화면에서 확인해 주세요.",
                "note": "행사장은 11:00에 열리며 러닝은 16:00까지 진행됩니다. 무대 행사 등 전체 일정은 주최 측 사정에 따라 변경될 수 있습니다.",
                "evidenceUrls": ["https://marvelrunkorea2026.com/", "https://marvelrunkorea2026.com/guide"],
            },
        },
    },
)


def _activities():
    return sa.table("activities", *[
        sa.column(name, kind) for name, kind in (
            ("id", sa.Integer()), ("category", sa.String()),
            ("representative_image_url", sa.Text()), ("sport_name", sa.String()),
            ("region", sa.String()), ("sigun", sa.String()), ("place_name", sa.String()),
            ("source", sa.String()), ("external_id", sa.String()), ("summary", sa.Text()),
            ("address", sa.String()), ("source_url", sa.Text()),
            ("starts_at", sa.DateTime()), ("ends_at", sa.DateTime()),
            ("metadata", sa.JSON()), ("last_synced_at", sa.DateTime()),
            ("is_active", sa.Boolean()),
        )
    ])


def _upsert_event(connection, activities, event):
    day = event["starts_at"].replace(hour=0, minute=0, second=0, microsecond=0)
    existing = connection.execute(sa.select(activities).where(
        activities.c.category == "event",
        sa.or_(activities.c.external_id == event["external_id"], sa.and_(
            activities.c.place_name == event["place_name"],
            activities.c.starts_at >= day,
            activities.c.starts_at < day + timedelta(days=1),
        )),
    ).order_by(
        sa.case((activities.c.source == "tourapi", 0),
                (activities.c.source.is_not(None), 1), else_=2),
        activities.c.id,
    ).limit(1)).mappings().first()
    if existing:
        # Preserve source text, IDs and user links; enrich only participation guidance.
        metadata = event["metadata"].copy()
        if existing["representative_image_url"] != event["representative_image_url"]:
            metadata.pop("imageType", None)
            metadata.pop("imageCaption", None)
        previous = existing["metadata"] if isinstance(existing["metadata"], dict) else {}
        connection.execute(activities.update().where(activities.c.id == existing["id"])
                           .values(metadata=previous | metadata))
        return
    connection.execute(activities.insert().values(event | {
        "category": "event", "region": "강원특별자치도", "source": None,
        "last_synced_at": None, "is_active": True,
    }))


def upgrade() -> None:
    connection = op.get_bind()
    activities = _activities()
    for event in PUBLIC_EVENTS:
        _upsert_event(connection, activities, event)


def downgrade() -> None:
    # Never delete events that users may already have saved or linked to missions.
    pass
