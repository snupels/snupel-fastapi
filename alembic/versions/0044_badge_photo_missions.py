"""Add two explicit badge missions without sharing existing mission stamps."""
import json
import sqlalchemy as sa
from alembic import op

revision = "0044_badge_photo_missions"
down_revision = "0043_submission_photos"
branch_labels = None
depends_on = None

# Frozen source identities, not environment-specific database IDs.
# Summit height: Korea Forest Service, board BBSMSTR_1845, article 3189829.
MISSIONS = [
    dict(source="tourapi", externalId="127649", region="동해", sport="MOUNTAIN",
         title="두타산 정상 방문 인증", duration=480,
         description="해발 1,353m 두타산 정상에 방문하는 산악 미션입니다. 산행 경험과 체력에 맞는 정규 탐방로를 선택하고, 기상·입산 통제·하산 시간을 반드시 확인해 주세요. 무리한 산행은 피하고 통제 시 참여하지 마세요.",
         proof="두타산 정상석의 이름과 높이를 확인할 수 있는 현장 사진, 본인의 정상 방문을 확인할 수 있는 사진을 제출해 주세요. 입구·전망대 사진만으로는 승인되지 않습니다.",
         prompt="두타산 정상석과 본인의 방문을 확인할 수 있는 사진",
         reward="동해 산악 스탬프 1개 · 승인 시 정상 정복자 배지",
         schedule="입산 허용 기간 · 기상·탐방로 통제 확인 필수",
         steps=["기상·입산 통제와 정규 탐방로 확인", "안전하게 정상 방문 후 인증 사진 촬영", "사진 제출 후 운영자 승인 확인"]),
    dict(source="tourapi", externalId="2710791", region="양양", sport="ATHLETICS",
         title="하조대 해변 일출 걷기 인증", duration=60,
         description="해파랑길 43코스의 하조대해변 구간에서 아침 바다를 보며 걷는 미션입니다. 전체 코스 완주는 필요하지 않습니다. 개방된 해변 산책 구간만 이용하고 파도·강풍과 출입 통제를 확인해 주세요. 방파제·갯바위에는 올라가지 마세요.",
         proof="하조대해변 위치를 확인할 수 있는 안내 표지 사진과 같은 방문에서 촬영한 일출 시간대의 바다·걷기 사진을 함께 제출해 주세요. 한 장에 모두 확인되어도 됩니다. 장소를 확인할 수 없는 바다 사진만으로는 승인되지 않습니다.",
         prompt="하조대해변 표지와 일출 시간대 걷기 사진",
         reward="양양 육상 스탬프 1개 · 승인 시 선라이즈 헌터 배지",
         schedule="현장 출입이 허용된 일출 시간대 · 기상 확인 필수",
         steps=["일출 시간과 해변 개방·기상 확인", "하조대해변 산책 후 장소·일출 사진 촬영", "사진 제출 후 운영자 승인 확인"]),
]


def upgrade():
    connection = op.get_bind()
    targets = []
    for mission in MISSIONS:
        activity = connection.execute(sa.text(
            "SELECT id, representative_image_url FROM activities WHERE source=:source "
            "AND external_id=:externalId AND is_active=1"
        ), mission).mappings().one()
        stamp = connection.execute(sa.text(
            "SELECT s.id FROM stamps s JOIN stamp_catalog sc ON sc.id=s.stamp_catalog_id "
            "WHERE sc.region_ko=:region AND sc.sport_en=:sport"
        ), mission).scalar_one()
        conflict = connection.execute(sa.text(
            "SELECT c.id FROM course_stamps cs JOIN courses c ON c.id=cs.course_id "
            "WHERE cs.stamp_id=:stamp AND c.title<>:title LIMIT 1"
        ), {"stamp": stamp, "title": mission["title"]}).scalar_one_or_none()
        if conflict is not None:
            raise RuntimeError("Badge mission stamp already belongs to another mission")
        targets.append((mission, activity, stamp))
    for mission, activity, stamp in targets:
        params = {**mission, "activity": activity["id"], "stamp": stamp,
                  "image": activity["representative_image_url"],
                  "steps": json.dumps(mission["steps"], ensure_ascii=False)}
        connection.execute(sa.text(
            "UPDATE stamps SET activity_id=:activity, description=:proof, "
            "updated_at=CURRENT_TIMESTAMP WHERE id=:stamp"
        ), params)
        connection.execute(sa.text(
            "INSERT INTO courses (category, sport_name, recommended_companion, representative_image_url, "
            "estimated_duration_minutes, theme, title, description, participation_period, "
            "proof_instructions, photo_prompt, reward_description, steps, is_published, created_at, updated_at) "
            "SELECT 'event', :sport, '동행 권장', :image, :duration, 'stamp', :title, :description, "
            ":schedule, :proof, :prompt, :reward, :steps, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            "WHERE NOT EXISTS (SELECT 1 FROM courses WHERE title=:title)"
        ), params)
        connection.execute(sa.text(
            "INSERT INTO course_stamps (course_id, stamp_id, position, created_at) "
            "SELECT c.id, :stamp, 1, CURRENT_TIMESTAMP FROM courses c WHERE c.title=:title "
            "AND NOT EXISTS (SELECT 1 FROM course_stamps cs WHERE cs.course_id=c.id AND cs.stamp_id=:stamp)"
        ), params)


def downgrade():
    for mission in MISSIONS:
        op.get_bind().execute(sa.text("UPDATE courses SET is_published=0 WHERE title=:title"), mission)
