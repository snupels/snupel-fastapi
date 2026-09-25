"""Keep feed deletion independent from mission awards."""
from alembic import op
import sqlalchemy as sa

revision = "0046_feed_deletion"
down_revision = "0045_retire_baekdu"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("stamp_submissions", sa.Column("feed_deleted_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("stamp_submissions", "feed_deleted_at")
