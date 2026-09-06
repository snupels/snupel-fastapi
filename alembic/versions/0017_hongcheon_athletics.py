"""Connect the Hongcheon marathon mission to the athletics stamp."""

import sqlalchemy as sa
from alembic import op

revision = "0017_hongcheon_athletics"
down_revision = "0016_feed_engagement"
branch_labels = None
depends_on = None

EVENT_EXTERNAL_ID = "official-2026-hongcheon-love-marathon"
MISSION_TITLE = "2026 홍천사랑마라톤 참가 인증"


def upgrade() -> None:
    bind = op.get_bind()
    params = {
        "external_id": EVENT_EXTERNAL_ID,
        "title": MISSION_TITLE,
        "description": "홍천사랑마라톤 참여 사진으로 대회 참가를 인증하세요.",
    }

    bind.execute(
        sa.text(
            "UPDATE stamps s "
            "JOIN stamp_catalog sc ON sc.id = s.stamp_catalog_id "
            "JOIN activities a ON a.external_id = :external_id "
            "SET s.activity_id = a.id, s.description = :description, "
            "s.image_url = a.representative_image_url, s.updated_at = CURRENT_TIMESTAMP "
            "WHERE sc.region_ko = '홍천' AND sc.sport_en = 'ATHLETICS'"
        ),
        params,
    )
    bind.execute(
        sa.text(
            "UPDATE stamps event_stamp "
            "JOIN activities a ON a.id = event_stamp.activity_id "
            "JOIN stamp_catalog sc ON sc.region_ko = '홍천' AND sc.sport_en = 'ATHLETICS' "
            "LEFT JOIN stamps catalog_stamp ON catalog_stamp.stamp_catalog_id = sc.id "
            "SET event_stamp.stamp_catalog_id = sc.id, event_stamp.description = :description, "
            "event_stamp.image_url = a.representative_image_url, "
            "event_stamp.updated_at = CURRENT_TIMESTAMP "
            "WHERE a.external_id = :external_id AND event_stamp.stamp_catalog_id IS NULL "
            "AND catalog_stamp.id IS NULL"
        ),
        params,
    )
    bind.execute(
        sa.text(
            "UPDATE stamp_submissions submission "
            "JOIN stamps event_stamp ON event_stamp.id = submission.stamp_id "
            "JOIN activities a ON a.id = event_stamp.activity_id AND a.external_id = :external_id "
            "JOIN stamp_catalog sc ON sc.region_ko = '홍천' AND sc.sport_en = 'ATHLETICS' "
            "JOIN stamps catalog_stamp ON catalog_stamp.stamp_catalog_id = sc.id "
            "SET submission.stamp_id = catalog_stamp.id "
            "WHERE event_stamp.stamp_catalog_id IS NULL"
        ),
        params,
    )
    bind.execute(
        sa.text(
            "INSERT IGNORE INTO collected_stamps (passport_id, stamp_id, collected_at) "
            "SELECT collected.passport_id, catalog_stamp.id, collected.collected_at "
            "FROM collected_stamps collected "
            "JOIN stamps event_stamp ON event_stamp.id = collected.stamp_id "
            "JOIN activities a ON a.id = event_stamp.activity_id AND a.external_id = :external_id "
            "JOIN stamp_catalog sc ON sc.region_ko = '홍천' AND sc.sport_en = 'ATHLETICS' "
            "JOIN stamps catalog_stamp ON catalog_stamp.stamp_catalog_id = sc.id "
            "WHERE event_stamp.stamp_catalog_id IS NULL"
        ),
        params,
    )
    bind.execute(
        sa.text(
            "DELETE collected FROM collected_stamps collected "
            "JOIN stamps event_stamp ON event_stamp.id = collected.stamp_id "
            "JOIN activities a ON a.id = event_stamp.activity_id "
            "WHERE a.external_id = :external_id AND event_stamp.stamp_catalog_id IS NULL"
        ),
        params,
    )
    bind.execute(
        sa.text(
            "DELETE course_stamp FROM course_stamps course_stamp "
            "JOIN courses course ON course.id = course_stamp.course_id "
            "WHERE course.title = :title"
        ),
        params,
    )
    bind.execute(
        sa.text(
            "INSERT INTO course_stamps (course_id, stamp_id, position, created_at) "
            "SELECT course.id, stamp.id, 1, CURRENT_TIMESTAMP FROM courses course "
            "JOIN stamp_catalog catalog "
            "ON catalog.region_ko = '홍천' AND catalog.sport_en = 'ATHLETICS' "
            "JOIN stamps stamp ON stamp.stamp_catalog_id = catalog.id "
            "WHERE course.title = :title"
        ),
        params,
    )
    bind.execute(
        sa.text(
            "DELETE event_stamp FROM stamps event_stamp "
            "JOIN activities a ON a.id = event_stamp.activity_id "
            "WHERE a.external_id = :external_id AND event_stamp.stamp_catalog_id IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM stamp_submissions submission "
            "WHERE submission.stamp_id = event_stamp.id)"
        ),
        params,
    )


def downgrade() -> None:
    # User progress is intentionally kept on the canonical athletics stamp.
    pass
