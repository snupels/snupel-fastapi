"""Add verified public-participation events without replacing tourism API data."""

from datetime import datetime, timedelta

import sqlalchemy as sa
from alembic import op

revision = "0039_public_sports_events"
down_revision = "0038_mission_badge_catalog"
branch_labels = None
depends_on = None

# Frozen, organizer-verified records only. Do not fetch websites during migration.
# activities uses timezone-naive local event dates, like the existing records;
# participation deadlines retain explicit Asia/Seoul offsets for UI comparison.
PUBLIC_EVENTS = (
    {
        "external_id": "official-2026-roundlab-run",
        "place_name": "2026 라운드랩 RUN", "sport_name": "러닝", "sigun": "춘천시",
        "address": "춘천 송암스포츠타운 종합경기장",
        "starts_at": datetime(2026, 11, 8, 9),
        "ends_at": datetime(2026, 11, 8, 23, 59, 59),
        "source_url": "https://kw-marathon.com/",
        "representative_image_url": "https://kw-marathon.com/theme/krf/img/01_02_roundlab.jpg",
        "summary": "춘천 의암호의 풍경을 따라 달리는 러닝 행사입니다. 하프·10km·5km 중 자신의 체력에 맞는 코스를 선택해 도전해 보세요.",
        "metadata": {
            "eventType": "sports", "officialSource": "서린컴퍼니·강원일보",
            "curationSource": "official_organizer",
            "participation": {
                "mode": "registration", "status": "open", "verifiedAt": "2026-09-08",
                "firstCome": True,
                "opensAt": "2026-08-07T10:00:00+09:00",
                "programs": "하프·10km·5km",
                "eligibility": "신체 건강한 일반인. 보호자 동반 등 세부 참가 조건은 공식 요강을 확인해 주세요.",
                "fee": "5km 45,000원 / 10km 50,000원 / 하프 55,000원",
                "registrationGuide": "8월 7일 10시부터 온라인 신청·결제 완료순 5,000명 선착순 접수. 현재 잔여석과 신청 가능 여부는 공식 홈페이지에서 확인해 주세요.",
                "note": "오전 8시 집결, 오전 9시 하프·10km·5km 순차 출발. 참가권 양도·대리 참가 불가.",
                "evidenceUrls": [
                    "https://kw-marathon.com/",
                    "https://kw-marathon.com/theme/krf/content/roundlab/01_05.php",
                ],
            },
        },
    },
    {
        "external_id": "official-2026-wonju-international-walking",
        "place_name": "제32회 원주국제걷기대회", "sport_name": "걷기", "sigun": "원주시",
        "address": "원주댄싱공연장 및 원주시 일원",
        "starts_at": datetime(2026, 10, 24),
        "ends_at": datetime(2026, 10, 25, 23, 59, 59),
        "source_url": "https://koreawalk.kr/",
        "representative_image_url": "https://koreawalk.kr/images/main_slide_2.jpg?v=20240923.1",
        "summary": "가을 원주의 자연을 걸어서 만나는 국제 걷기 행사입니다. 5km부터 30km까지 코스를 골라 가족·친구와 함께 참여해 보세요.",
        "metadata": {
            "eventType": "sports", "officialSource": "대한걷기연맹",
            "curationSource": "official_organizer", "imageType": "photo",
            "imageCaption": "대한걷기연맹 공식 홈페이지에 게시된 이전 행사 사진입니다.",
            "participation": {
                "mode": "registration", "status": "open", "verifiedAt": "2026-09-08",
                "opensAt": "2026-08-03T00:00:00+09:00",
                "closesAt": "2026-10-22T21:00:00+09:00", "onsiteAvailable": True,
                "programs": "양일 각각 5km·10km·20km·30km",
                "eligibility": "남녀노소 누구나. 30km 코스는 중학생 이상 참가 가능합니다.",
                "fee": "일반 1인 10,000원. 단체·학생 할인과 장애인 무료 기준은 공식 안내 참고.",
                "registrationGuide": "10월 22일 21시까지 인터넷·방문 접수. 행사 당일 현장 접수도 가능합니다(현장 현금 결제).",
                "evidenceUrls": [
                    "https://koreawalk.kr/intro/summary.html",
                    "https://koreawalk.kr/intro/regi_guide.html",
                ],
            },
        },
    },
    {
        "external_id": "official-2026-uiamho-paddle-festa",
        "place_name": "2026 의암호 패들보드 페스타", "sport_name": "수상레저", "sigun": "춘천시",
        "address": "춘천 의암호·송암스포츠타운 일원 (체험 접수: 송암동 641)",
        "starts_at": datetime(2026, 9, 19),
        "ends_at": datetime(2026, 9, 20, 23, 59, 59),
        "source_url": "https://www.mullegil.com/mullegil/web/product/choice.php?catcode=110000000000",
        "representative_image_url": "https://www.mullegil.com/data/mullegil/item/1787703402/thumb/thumb_R_1.png",
        "summary": "의암호에서 SUP와 카누, 카약 등 다양한 수상 레저를 직접 즐기는 체험 축제입니다. 가족·친구와 함께 원하는 종목을 골라 참여해 보세요.",
        "metadata": {
            "eventType": "sports", "officialSource": "춘천레저·태권도조직위원회·물레길",
            "curationSource": "official_organizer", "imageType": "poster",
            "participation": {
                "mode": "registration", "status": "open", "firstCome": True,
                "verifiedAt": "2026-09-08",
                "programs": "SUP·카누·카약·요트·수상자전거 체험",
                "eligibility": "체험 예약 상품은 만 3세 이상 대상입니다. 종목별 안전·탑승 기준과 보호자 동반 조건은 예약 안내를 확인해 주세요.",
                "fee": "자유이용권 총 1인 10,000원(춘천사랑상품권 10,000원 교환 안내).",
                "registrationGuide": "물레길 공식 안내의 네이버 예약으로 신청합니다. 선착순 모집이며 잔여석·판매 종료 여부는 공식 예약 페이지에서 확인해 주세요.",
                "note": "예약 화면의 100원 외 별도 입금 9,900원이 안내되어 있습니다. 총액·입금 및 환불 조건을 꼭 확인해 주세요. 종목별 시간 예약 없이 현장에서 체험 종목을 선택하는 방식입니다.",
                "evidenceUrls": [
                    "https://www.clt.or.kr/kr/contents?cid=c65c74149eb74a14a3fc630aa38e5c53",
                    "https://www.mullegil.com/mullegil/web/product/choice.php?catcode=110000000000",
                    "https://booking.naver.com/booking/12/bizes/195575/items/3011325?area=ple&lang=ko&startDateTime=2026-09-19T00:00:00%2B09:00&theme=place",
                ],
            },
        },
    },
    {
        "external_id": "official-2026-yunseul-sunset-canoe",
        "place_name": "2026 시민레저이벤트 윤슬노을카누", "sport_name": "카누", "sigun": "춘천시",
        "address": "춘천시요트협회 (춘천시 송암동 684)",
        "starts_at": datetime(2026, 9, 19, 15),
        "ends_at": datetime(2026, 9, 20, 19),
        "source_url": "https://event-us.kr/byulhacompany/event/132807",
        "representative_image_url": "https://eventusstorage.blob.core.windows.net/evs/Image/byulhacompany/132807/ProjectInfo/Cover/ca9e7122d39642eaa9c210eba960d89a.png",
        "summary": "윤슬과 노을이 펼쳐지는 의암호에서 함께 노를 젓는 가을 카누 체험입니다. 하루 세 가지 시간대 중 원하는 풍경을 골라 참여할 수 있습니다.",
        "metadata": {
            "eventType": "sports", "officialSource": "춘천레저·태권도조직위원회·별하컴퍼니",
            "curationSource": "official_organizer", "imageType": "poster",
            "participation": {
                "mode": "registration", "status": "open", "firstCome": True,
                "verifiedAt": "2026-09-08",
                "opensAt": "2026-08-31T10:00:00+09:00",
                "closesAt": "2026-09-11T18:00:00+09:00",
                "programs": "윤슬 15:00~16:00 / 윤슬·노을 16:30~17:30 / 노을 18:00~19:00 (양일 운영)",
                "eligibility": "5세 미만 탑승 불가. 만 10세 미만은 보호자 동반 무료. 카누 1대 최대 3인·합산 210kg 이하이며 아동 동반 기준은 신청 안내를 확인해 주세요.",
                "fee": "1인 10,000원, 기본 2인 결제 20,000원. 인원 구성에 따라 총액이 달라집니다.",
                "registrationGuide": "9월 11일 18시까지 주최 측 이벤터스에서 신청합니다. 회당 약 25팀 선착순으로, 회차별 잔여석·대기 접수 여부를 확인해 주세요.",
                "note": "모집 기한과 무료 환불 기한이 같습니다. 결제·참가 확정 안내 및 안전 탑승 조건을 확인한 뒤 신청해 주세요.",
                "evidenceUrls": [
                    "https://www.clt.or.kr/kr/contents?cid=c65c74149eb74a14a3fc630aa38e5c53",
                    "https://event-us.kr/byulhacompany/event/132807",
                ],
            },
        },
    },
)
EXISTING_EVENT_METADATA = {
    "official-2026-chuncheon-marathon": {
        "participation": {
            "mode": "registration", "status": "closed", "verifiedAt": "2026-09-08",
            "programs": "풀코스(42.195km) · 10km",
            "registrationGuide": "참가 신청이 마감되었습니다. 추가 접수 여부는 공식 공지를 확인해 주세요.",
            "evidenceUrls": [
                "https://www.chuncheonmarathon.com/apply/part-application.html",
                "https://www.chuncheonmarathon.com/",
            ],
        },
    },
    "official-2026-hongcheon-love-marathon": {
        "officialSource": "홍천군육상연맹",
        "participation": {
            "mode": "registration", "status": "check", "verifiedAt": "2026-09-08",
            "programs": "하프 · 10km · 5km",
            "eligibility": "하프: 만 18세 이상. 10km·5km: 참가 제한 없음(시상 제외 기준은 공식 요강 확인).",
            "fee": "하프·10km 50,000원 / 5km 45,000원",
            "registrationGuide": "공식 홈페이지 온라인 접수. 결제 완료순 3,000명 선착순으로, 현재 잔여 인원과 접수 가능 여부는 공식 사이트에서 확인해 주세요.",
            "note": "공식 안내의 환불 신청 기한은 2026.09.04 17:00입니다. 신청 전 취소·환불 조건을 확인해 주세요.",
            "evidenceUrls": ["https://www.hongcheonrun.net/", "https://www.hongcheonrun.net/entryperson.php"],
        },
    },
    "official-2026-chuncheon-world-poomsae": {
        "participation": {
            "mode": "spectator", "status": "check", "verifiedAt": "2026-09-08",
            "programs": "세계태권도품새선수권대회",
            "registrationGuide": "경기 일정과 관람·입장 안내는 대회 공식 홈페이지에서 확인해 주세요.",
            "note": "일반인 체험행사 접수와 경기 참가 선수 등록은 구분하여 확인해 주세요.",
            "evidenceUrls": ["https://cc2026wtpc.com/"],
        },
    },
}


def _activities():
    return sa.table(
        "activities",
        sa.column("id", sa.Integer()),
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


def _merge_metadata(connection, activities, row, metadata):
    existing = row["metadata"] if isinstance(row["metadata"], dict) else {}
    connection.execute(
        activities.update().where(activities.c.id == row["id"])
        .values(metadata=existing | metadata)
    )


def _upsert_event(connection, activities, event):
    day_start = event["starts_at"].replace(hour=0, minute=0, second=0, microsecond=0)
    same_event = sa.and_(
        activities.c.place_name == event["place_name"],
        activities.c.starts_at >= day_start,
        activities.c.starts_at < day_start + timedelta(days=1),
    )
    existing = connection.execute(
        sa.select(activities).where(
            activities.c.category == "event",
            sa.or_(activities.c.external_id == event["external_id"], same_event),
        ).order_by(
            sa.case((activities.c.source == "tourapi", 0),
                    (activities.c.source.is_not(None), 1), else_=2),
            activities.c.id,
        ).limit(1)
    ).mappings().first()
    if existing:
        # Keep the API row/ID, original title, dates, image, URL and source.
        # Official participation guidance is supplemental, not an API rewrite.
        metadata = event["metadata"].copy()
        if existing["representative_image_url"] != event.get("representative_image_url"):
            metadata.pop("imageType", None)
            metadata.pop("imageCaption", None)
        _merge_metadata(connection, activities, existing, metadata)
        return
    connection.execute(activities.insert().values(
        event | {"category": "event", "region": "강원특별자치도", "source": None,
                 "last_synced_at": None, "is_active": True}
    ))


def upgrade() -> None:
    connection = op.get_bind()
    activities = _activities()
    for external_id, metadata in EXISTING_EVENT_METADATA.items():
        rows = connection.execute(sa.select(activities).where(
            activities.c.category == "event", activities.c.external_id == external_id,
            activities.c.source.is_(None),
        )).mappings().all()
        for row in rows:
            _merge_metadata(connection, activities, row, metadata)
    for event in PUBLIC_EVENTS:
        _upsert_event(connection, activities, event)


def downgrade() -> None:
    # Event IDs may already be saved or used by missions; preserve those links.
    pass
