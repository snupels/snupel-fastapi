"""Add opt-in community feed fields to stamp submissions."""

import sqlalchemy as sa

from alembic import op

revision = "0009_submission_community_feed"
down_revision = "0008_stampbook"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stamp_submissions",
        sa.Column(
            "share_to_feed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "stamp_submissions",
        sa.Column("feed_caption", sa.String(length=300)),
    )
    op.create_index(
        "stamp_submissions_feed_idx",
        "stamp_submissions",
        ["status", "share_to_feed", "reviewed_at"],
    )


def downgrade() -> None:
    op.drop_index("stamp_submissions_feed_idx", table_name="stamp_submissions")
    op.drop_column("stamp_submissions", "feed_caption")
    op.drop_column("stamp_submissions", "share_to_feed")
