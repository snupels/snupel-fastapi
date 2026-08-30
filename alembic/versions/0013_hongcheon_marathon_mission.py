"""Add Hongcheon marathon mission and GPS proof fields."""

import sqlalchemy as sa
from alembic import op

revision = "0013_hongcheon_marathon_mission"
down_revision = "0012_user_phone_number"
branch_labels = None
depends_on = None

EVENT_EXTERNAL_ID = "official-2026-hongcheon-love-marathon"
MISSION_TITLE = "2026 홍천사랑마라톤 참가 인증"
EVENT_LATITUDE = 37.7093900
EVENT_LONGITUDE = 127.9063000


def upgrade() -> None:
    op.add_column("stamp_submissions", sa.Column("latitude", sa.Numeric(10, 7)))
    op.add_column("stamp_submissions", sa.Column("longitude", sa.Numeric(10, 7)))
    op.add_column("stamp_submissions", sa.Column("gps_accuracy_m", sa.Numeric(8, 2)))
    op.add_column("stamp_submissions", sa.Column("captured_at", sa.DateTime()))

    op.execute(
        sa.text(
            "UPDATE activities SET latitude = :latitude, longitude = :longitude "
            "WHERE external_id = :external_id"
        ).bindparams(
            latitude=EVENT_LATITUDE,
            longitude=EVENT_LONGITUDE,
            external_id=EVENT_EXTERNAL_ID,
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO stamps (activity_id, description, image_url, created_at, updated_at) "
            "SELECT a.id, :description, a.representative_image_url, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            "FROM activities a WHERE a.external_id = :external_id "
            "AND NOT EXISTS (SELECT 1 FROM stamps s WHERE s.activity_id = a.id)"
        ).bindparams(
            description="홍천종합운동장에서 GPS와 현장 사진으로 대회 참가를 인증하세요.",
            external_id=EVENT_EXTERNAL_ID,
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO courses (category, sport_name, recommended_companion, representative_image_url, "
            "estimated_duration_minutes, theme, title, description, is_published, created_at, updated_at) "
            "SELECT 'event', NULL, '마라톤 참가자', a.representative_image_url, 60, 'stamp', :title, "
            ":description, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP FROM activities a "
            "WHERE a.external_id = :external_id "
            "AND NOT EXISTS (SELECT 1 FROM courses c WHERE c.title = :title)"
        ).bindparams(
            title=MISSION_TITLE,
            description="2026 홍천사랑마라톤 현장에서 GPS 위치와 참가 사진을 제출하면 검토 후 스탬프를 받을 수 있습니다.",
            external_id=EVENT_EXTERNAL_ID,
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO course_stamps (course_id, stamp_id, position, created_at) "
            "SELECT c.id, s.id, 1, CURRENT_TIMESTAMP FROM courses c "
            "JOIN activities a ON a.external_id = :external_id "
            "JOIN stamps s ON s.activity_id = a.id WHERE c.title = :title "
            "AND NOT EXISTS (SELECT 1 FROM course_stamps cs WHERE cs.course_id = c.id AND cs.stamp_id = s.id)"
        ).bindparams(title=MISSION_TITLE, external_id=EVENT_EXTERNAL_ID)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE cs FROM course_stamps cs JOIN courses c ON c.id = cs.course_id "
            "WHERE c.title = :title"
        ).bindparams(title=MISSION_TITLE)
    )
    op.execute(sa.text("DELETE FROM courses WHERE title = :title").bindparams(title=MISSION_TITLE))
    op.execute(
        sa.text(
            "DELETE s FROM stamps s JOIN activities a ON a.id = s.activity_id "
            "WHERE a.external_id = :external_id AND s.stamp_catalog_id IS NULL"
        ).bindparams(external_id=EVENT_EXTERNAL_ID)
    )
    op.execute(
        sa.text(
            "UPDATE activities SET latitude = NULL, longitude = NULL WHERE external_id = :external_id"
        ).bindparams(external_id=EVENT_EXTERNAL_ID)
    )
    op.drop_column("stamp_submissions", "captured_at")
    op.drop_column("stamp_submissions", "gps_accuracy_m")
    op.drop_column("stamp_submissions", "longitude")
    op.drop_column("stamp_submissions", "latitude")
