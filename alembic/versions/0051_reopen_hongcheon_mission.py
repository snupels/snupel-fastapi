"""Allow post-event Hongcheon marathon photo certification."""
from alembic import op
import sqlalchemy as sa

revision = "0051_reopen_hongcheon_mission"
down_revision = "0050_close_hongcheon_mission"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().execute(sa.text(
        "UPDATE courses SET is_closed = :closed, participation_period = :period "
        "WHERE title = :title AND category = 'event' AND id IN ("
        "SELECT cs.course_id FROM course_stamps cs "
        "JOIN stamps s ON s.id = cs.stamp_id "
        "JOIN activities a ON a.id = s.activity_id WHERE a.external_id = :external_id)"
    ), {
        "closed": False,
        "period": "2026.10.04 행사 참가 사진은 행사 종료 후에도 인증 신청할 수 있습니다.",
        "title": "2026 홍천사랑마라톤 참가 인증",
        "external_id": "official-2026-hongcheon-love-marathon",
    })


def downgrade():
    # Keep the owner's explicit decision to accept post-event submissions.
    # No records or schema are removed by this data-only migration.
    pass
