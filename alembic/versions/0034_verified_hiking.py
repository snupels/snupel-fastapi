"""Add curated, named hiking routes without restoring mountain100 placeholders."""

import json

import sqlalchemy as sa
from alembic import op

revision = "0034_verified_hiking"
down_revision = "0033_photo_missions"
branch_labels = None
depends_on = None

REFERENCE = "https://tour.pc.go.kr/Home/H10000/H10200/placeDetail?place_no=166"
ROUTES = [
    ("odae-birobong", "오대산 비로봉 등산로", "상원사", "상원사 → 중대사 → 적멸보궁 → 비로봉", "3.4km", "약 1시간 40분", "편도"),
    ("odae-sangwangbong", "오대산 상왕봉 등산로", "상원사", "상원사 → 비로봉 → 상왕봉 → 두로령 → 북대사 → 상원사", "14.1km", "약 5시간 30분", "순환"),
    ("odae-dongdaesan", "오대산 동대산 등산로", "진고개", "진고개 → 동대산 → 동피골", "4.4km", "약 2시간 10분", "편도·종점 다름"),
    ("odae-durobong", "오대산 두로봉 등산로", "진고개", "진고개 → 동대산 → 두로봉 → 두로령", "10km", "약 4시간 40분", "편도·종점 다름"),
    ("gyebangsan-course-1", "계방산 제1 등산로", "운두령", "운두령 → 계방산 정상 → 이승복 생가 입구", "8.9km", "약 6시간", "편도·종점 다름"),
]


def upgrade() -> None:
    connection = op.get_bind()
    for key, name, start, route, distance, duration, direction in ROUTES:
        summary = (
            f"등산 코스: {route}\n출발 지점: {start}\n"
            f"안내 거리: {distance} ({direction}) · 예상 소요시간: {duration}\n"
            "편도 코스는 복귀 이동 계획이 필요합니다. 소요시간은 휴식·날씨·체력에 따라 달라집니다.\n"
            "방문 전 국립공원공단에서 탐방로 통제와 입산 가능 시간을 확인하세요. "
            "현재 개방 상태를 보장하는 안내가 아닙니다.\n"
            "자료: 평창문화관광 오대산국립공원 등산로 안내 (2026-09-07 확인)."
        )
        # Curated entries intentionally use NULL source: the 10-day expiry applies
        # to automated feeds, not manually verified routes. Provenance is retained.
        connection.execute(sa.text(
            "INSERT INTO activities (category, sport_name, region, sigun, place_name, "
            "address, summary, source_url, external_id, metadata, is_active, created_at, updated_at) "
            "SELECT 'sports', 'hiking', '강원특별자치도', '평창군', :name, :address, "
            ":summary, :url, :key, :metadata, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            "WHERE NOT EXISTS (SELECT 1 FROM activities WHERE external_id = :key)"
        ), {
            "key": f"verified-hiking-{key}", "name": name,
            "address": f"강원특별자치도 평창군 {'용평면' if start == '운두령' else '진부면'} {start} (등산 시작점)",
            "summary": summary,
            "url": "https://www.knps.or.kr/front/portal/visit/visitCourseMain.do?menuNo=7020096&parkId=120900",
            "metadata": json.dumps({
                "curated_source": REFERENCE, "verified_at": "2026-09-07",
                "route": route, "trailhead": start, "distance": distance,
                "duration": duration, "direction": direction,
                "facility_type": "등산로",
            }, ensure_ascii=False),
        })


def downgrade() -> None:
    for key, *_ in ROUTES:
        op.get_bind().execute(sa.text(
            "UPDATE activities SET is_active = 0 WHERE external_id = :key"
        ), {"key": f"verified-hiking-{key}"})
