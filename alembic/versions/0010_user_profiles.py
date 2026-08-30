"""Add user profiles and password reset codes."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0010_user_profiles"
down_revision = "0009_submission_community_feed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("nickname", sa.String(length=30)))
    op.add_column("users", sa.Column("profile_image_key", sa.String(length=500)))
    op.create_table(
        "password_reset_codes",
        sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column("user_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "password_reset_codes_user_idx",
        "password_reset_codes",
        ["user_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("password_reset_codes_user_idx", table_name="password_reset_codes")
    op.drop_table("password_reset_codes")
    op.drop_column("users", "profile_image_key")
    op.drop_column("users", "nickname")
