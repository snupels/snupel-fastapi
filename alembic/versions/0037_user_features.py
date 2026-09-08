"""Add private user activity, badge rules, rewards, and mission operations fields."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0037_user_features"
down_revision = "0036_community_follow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("badges", sa.Column("rule_key", sa.String(50), nullable=True))
    op.create_unique_constraint("badges_rule_key_unique", "badges", ["rule_key"])

    op.add_column("courses", sa.Column("participation_period", sa.String(255), nullable=True))
    op.add_column("courses", sa.Column("proof_instructions", sa.Text(), nullable=True))
    op.add_column("courses", sa.Column("photo_prompt", sa.Text(), nullable=True))
    op.add_column("courses", sa.Column("reward_description", sa.Text(), nullable=True))
    op.add_column("courses", sa.Column("steps", sa.JSON(), nullable=True))
    op.add_column("courses", sa.Column("official_url", sa.Text(), nullable=True))
    op.add_column("courses", sa.Column("official_label", sa.String(100), nullable=True))

    op.create_table(
        "saved_activities",
        sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            mysql.BIGINT(unsigned=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "activity_id",
            mysql.BIGINT(unsigned=True),
            sa.ForeignKey("activities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "activity_id", name="saved_activities_user_activity_unique"
        ),
    )
    op.create_index("saved_activities_activity_id_idx", "saved_activities", ["activity_id"])

    op.create_table(
        "reward_claims",
        sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            mysql.BIGINT(unsigned=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("milestone", sa.Enum("badge_6", "badge_12"), nullable=False),
        sa.Column("recipient_name", sa.String(100), nullable=False),
        sa.Column("phone_number", sa.String(30), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("eligible", "requested", "preparing", "shipped", "completed"),
            server_default="requested",
            nullable=False,
        ),
        sa.Column("requested_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("fulfilled_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "user_id", "milestone", name="reward_claims_user_milestone_unique"
        ),
    )
    op.create_index("reward_claims_status_idx", "reward_claims", ["status"])


def downgrade() -> None:
    op.drop_index("reward_claims_status_idx", table_name="reward_claims")
    op.drop_table("reward_claims")
    op.drop_index("saved_activities_activity_id_idx", table_name="saved_activities")
    op.drop_table("saved_activities")
    for column in (
        "official_label",
        "official_url",
        "steps",
        "reward_description",
        "photo_prompt",
        "proof_instructions",
        "participation_period",
    ):
        op.drop_column("courses", column)
    op.drop_constraint("badges_rule_key_unique", "badges", type_="unique")
    op.drop_column("badges", "rule_key")
