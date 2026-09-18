"""Hide the four retired Baekdudaegan courses without deleting related records."""
from alembic import op
import sqlalchemy as sa

revision = "0045_retire_baekdu"
down_revision = "0044_badge_photo_missions"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().execute(sa.text(
        "UPDATE activities SET is_active = 0, updated_at = CURRENT_TIMESTAMP "
        "WHERE source = 'forest_baekdu' "
        "AND external_id IN ('BAEK_34', 'BAEK_36', 'BAEK_37', 'BAEK_38')"
    ))


def downgrade():
    # Never automatically republish explicitly retired tourism records.
    pass
