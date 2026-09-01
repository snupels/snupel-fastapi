"""Remove user GPS data from stamp submissions."""

import sqlalchemy as sa
from alembic import op

revision = "0014_remove_submission_gps"
down_revision = "0013_hongcheon_marathon_mission"
branch_labels = None
depends_on = None

MISSION_TITLE = "2026 홍천사랑마라톤 참가 인증"


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE courses SET description = :description WHERE title = :title"
        ).bindparams(
            title=MISSION_TITLE,
            description="2026 홍천사랑마라톤 참여 사진을 제출하면 검토 후 스탬프를 받을 수 있습니다.",
        )
    )
    op.execute(
        sa.text(
            "UPDATE stamps SET description = :description WHERE activity_id IN ("
            "SELECT id FROM activities WHERE external_id = :external_id)"
        ).bindparams(
            description="홍천사랑마라톤 참여 사진으로 대회 참가를 인증하세요.",
            external_id="official-2026-hongcheon-love-marathon",
        )
    )
    op.drop_column("stamp_submissions", "captured_at")
    op.drop_column("stamp_submissions", "gps_accuracy_m")
    op.drop_column("stamp_submissions", "longitude")
    op.drop_column("stamp_submissions", "latitude")


def downgrade() -> None:
    op.add_column("stamp_submissions", sa.Column("latitude", sa.Numeric(10, 7)))
    op.add_column("stamp_submissions", sa.Column("longitude", sa.Numeric(10, 7)))
    op.add_column("stamp_submissions", sa.Column("gps_accuracy_m", sa.Numeric(8, 2)))
    op.add_column("stamp_submissions", sa.Column("captured_at", sa.DateTime()))
    op.execute(
        sa.text(
            "UPDATE courses SET description = :description WHERE title = :title"
        ).bindparams(
            title=MISSION_TITLE,
            description="2026 홍천사랑마라톤 현장에서 GPS 위치와 참가 사진을 제출하면 검토 후 스탬프를 받을 수 있습니다.",
        )
    )
