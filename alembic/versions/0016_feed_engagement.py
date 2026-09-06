"""Add likes and comments to the community feed."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import BIGINT

revision = "0016_feed_engagement"
down_revision = "0015_pyeongchang_olympic_museum_mission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feed_likes",
        sa.Column("id", BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column("submission_id", BIGINT(unsigned=True), sa.ForeignKey("stamp_submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", BIGINT(unsigned=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("submission_id", "user_id", name="feed_likes_submission_user_unique"),
    )
    op.create_index("feed_likes_submission_idx", "feed_likes", ["submission_id"])
    op.create_table(
        "feed_comments",
        sa.Column("id", BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column("submission_id", BIGINT(unsigned=True), sa.ForeignKey("stamp_submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", BIGINT(unsigned=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("feed_comments_submission_idx", "feed_comments", ["submission_id", "created_at"])


def downgrade() -> None:
    op.drop_table("feed_comments")
    op.drop_table("feed_likes")
