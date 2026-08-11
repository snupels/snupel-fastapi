"""Add primary and sports categories to courses."""

import sqlalchemy as sa
from alembic import op

revision = "0007_course_categories"
down_revision = "0006_event_sources_and_sports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column(
            "category",
            sa.Enum("tour", "sports", "event"),
            nullable=False,
            server_default="tour",
        ),
    )
    op.add_column("courses", sa.Column("sport_name", sa.String(100)))


def downgrade() -> None:
    op.drop_column("courses", "sport_name")
    op.drop_column("courses", "category")
