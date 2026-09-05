"""Add the Pyeongchang Olympic museum photo mission."""

import sqlalchemy as sa
from alembic import op

revision = "0015_pyeongchang_olympic_museum_mission"
down_revision = "0014_remove_submission_gps"
branch_labels = None
depends_on = None

ACTIVITY_SOURCE = "tourapi"
ACTIVITY_EXTERNAL_ID = "2733036"
MISSION_TITLE = "2018 평창동계올림픽대회 및 동계패럴림픽대회 기념관 방문 인증"


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE stamps s "
            "JOIN stamp_catalog sc ON sc.id = s.stamp_catalog_id "
            "JOIN activities a ON a.source = :source AND a.external_id = :external_id "
            "SET s.activity_id = a.id, s.description = :description, "
            "s.image_url = a.representative_image_url, s.updated_at = CURRENT_TIMESTAMP "
            "WHERE sc.region_ko = '평창' AND sc.sport_en = 'OLYMPIC'"
        ).bindparams(
            source=ACTIVITY_SOURCE,
            external_id=ACTIVITY_EXTERNAL_ID,
            description="기념관 포토존 앞에서 촬영한 사진으로 방문을 인증하세요.",
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO stamps (activity_id, stamp_catalog_id, description, image_url, created_at, updated_at) "
            "SELECT a.id, sc.id, :description, a.representative_image_url, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            "FROM activities a JOIN stamp_catalog sc "
            "ON sc.region_ko = '평창' AND sc.sport_en = 'OLYMPIC' "
            "WHERE a.source = :source AND a.external_id = :external_id "
            "AND NOT EXISTS (SELECT 1 FROM stamps s WHERE s.stamp_catalog_id = sc.id)"
        ).bindparams(
            source=ACTIVITY_SOURCE,
            external_id=ACTIVITY_EXTERNAL_ID,
            description="기념관 포토존 앞에서 촬영한 사진으로 방문을 인증하세요.",
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO courses (category, sport_name, recommended_companion, representative_image_url, "
            "estimated_duration_minutes, theme, title, description, is_published, created_at, updated_at) "
            "SELECT 'event', NULL, '올림픽 역사·문화 체험 방문객', a.representative_image_url, "
            "30, 'stamp', :title, :description, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            "FROM activities a WHERE a.source = :source AND a.external_id = :external_id "
            "AND NOT EXISTS (SELECT 1 FROM courses c WHERE c.title = :title)"
        ).bindparams(
            source=ACTIVITY_SOURCE,
            external_id=ACTIVITY_EXTERNAL_ID,
            title=MISSION_TITLE,
            description=(
                "2018 평창동계올림픽대회 및 동계패럴림픽대회 기념관 포토존 앞에서 "
                "촬영한 사진을 제출하면 검토 후 스탬프 1개를 받을 수 있습니다."
            ),
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO course_stamps (course_id, stamp_id, position, created_at) "
            "SELECT c.id, s.id, 1, CURRENT_TIMESTAMP FROM courses c "
            "JOIN stamp_catalog sc ON sc.region_ko = '평창' AND sc.sport_en = 'OLYMPIC' "
            "JOIN stamps s ON s.stamp_catalog_id = sc.id WHERE c.title = :title "
            "AND NOT EXISTS (SELECT 1 FROM course_stamps cs "
            "WHERE cs.course_id = c.id AND cs.stamp_id = s.id)"
        ).bindparams(title=MISSION_TITLE)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE cs FROM course_stamps cs JOIN courses c ON c.id = cs.course_id "
            "WHERE c.title = :title"
        ).bindparams(title=MISSION_TITLE)
    )
    op.execute(sa.text("DELETE FROM courses WHERE title = :title").bindparams(title=MISSION_TITLE))
