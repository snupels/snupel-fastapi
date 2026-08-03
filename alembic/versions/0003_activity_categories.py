"""Normalize activity categories into tour, sports, and event."""

from alembic import op


revision = "0003_activity_categories"
down_revision = "0003_activity_sigun"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE activities MODIFY category "
        "ENUM('tour','sports','event','festival','tourism') NOT NULL"
    )
    op.execute("UPDATE activities SET category = 'tour' WHERE category = 'tourism'")
    op.execute("UPDATE activities SET category = 'event' WHERE category = 'festival'")
    op.execute("ALTER TABLE activities MODIFY category ENUM('tour','sports','event') NOT NULL")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE activities MODIFY category "
        "ENUM('tour','sports','event','festival','tourism') NOT NULL"
    )
    op.execute("UPDATE activities SET category = 'tourism' WHERE category = 'tour'")
    op.execute(
        "ALTER TABLE activities MODIFY category ENUM('sports','event','festival','tourism') NOT NULL"
    )
