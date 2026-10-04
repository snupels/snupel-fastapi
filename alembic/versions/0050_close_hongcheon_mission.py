"""Close Hongcheon marathon certification without changing existing awards."""
from alembic import op
import sqlalchemy as sa

revision = "0050_close_hongcheon_mission"
down_revision = "0049_autumn_sports_events"
branch_labels = None
depends_on = None

MISSION_TITLE = "2026 홍천사랑마라톤 참가 인증"
EVENT_EXTERNAL_ID = "official-2026-hongcheon-love-marathon"


def _close_mission(connection):
    connection.execute(sa.text(
        "UPDATE courses SET is_closed = :closed, participation_period = :period "
        "WHERE title = :title AND category = 'event' AND id IN ("
        "SELECT cs.course_id FROM course_stamps cs "
        "JOIN stamps s ON s.id = cs.stamp_id "
        "JOIN activities a ON a.id = s.activity_id WHERE a.external_id = :external_id)"
    ), {"closed": True, "period": "2026.10.04 마감", "title": MISSION_TITLE,
        "external_id": EVENT_EXTERNAL_ID})


def upgrade():
    op.add_column("courses", sa.Column("is_closed", sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
    _close_mission(op.get_bind())


def downgrade():
    # Do not silently reopen a closed mission by removing its enforcement field.
    raise RuntimeError("Mission closure requires an explicit data-preserving rollback plan.")
