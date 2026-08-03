"""Add sigun to activities."""

import sqlalchemy as sa
from alembic import op

revision = "0003_activity_sigun"
down_revision = "0002_tourism_missions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("activities", sa.Column("sigun", sa.String(100)))


def downgrade() -> None:
    op.drop_column("activities", "sigun")
