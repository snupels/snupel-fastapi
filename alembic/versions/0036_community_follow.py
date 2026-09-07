"""Community follows and non-reward operator demo posts."""
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import BIGINT
from alembic import op

revision = "0036_community_follow"
down_revision = "0035_remove_curated_hiking"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_follows",
        sa.Column("follower_id", BIGINT(unsigned=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("followed_id", BIGINT(unsigned=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("follower_id <> followed_id", name="no_self_follow"),
    )
    op.create_index("ix_user_follows_followed_id", "user_follows", ["followed_id"])
    op.alter_column("stamp_submissions", "passport_id", existing_type=BIGINT(unsigned=True), nullable=True)
    op.alter_column("stamp_submissions", "stamp_id", existing_type=BIGINT(unsigned=True), nullable=True)
    op.add_column("stamp_submissions", sa.Column("author_id", BIGINT(unsigned=True), nullable=True))
    op.create_foreign_key("submission_demo_author_fk", "stamp_submissions", "users", ["author_id"], ["id"], ondelete="CASCADE")
    op.add_column("stamp_submissions", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default="0"))
    op.create_check_constraint("submission_kind_valid", "stamp_submissions",
        "(is_demo = 0 AND passport_id IS NOT NULL AND stamp_id IS NOT NULL AND author_id IS NULL) OR "
        "(is_demo = 1 AND passport_id IS NULL AND stamp_id IS NULL AND author_id IS NOT NULL)")
    from app.config import admins
    from scripts.seed_community_demo import seed_demo
    print("community_demo=" + seed_demo(op.get_bind(), admins()))


def downgrade():
    raise RuntimeError("Community data must be archived before removing this schema.")
