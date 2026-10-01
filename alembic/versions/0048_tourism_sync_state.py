"""Track source sync progress and upstream visibility."""

from alembic import op
import sqlalchemy as sa

revision = "0048_tourism_sync_state"
down_revision = "0047_kakao_email"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "activities",
        sa.Column("upstream_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "sync_state",
        sa.Column("source", sa.String(50), primary_key=True),
        sa.Column("last_success_date", sa.Date()),
        sa.Column("last_success_at", sa.DateTime()),
        sa.Column("item_count", sa.Integer()),
        sa.Column("last_error", sa.Text()),
    )


def downgrade():
    op.drop_table("sync_state")
    op.drop_column("activities", "upstream_visible")
