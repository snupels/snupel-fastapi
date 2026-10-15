"""Open owner-approved five-stamp tee applications, capped at 100 lifetime slots."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import BIGINT

revision = "0052_passport_tee_rewards"
down_revision = "0051_reopen_hongcheon_mission"
branch_labels = None
depends_on = None


def upgrade():
    campaigns = op.create_table(
        "passport_reward_campaigns",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("required_stamps", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("claimed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint(
            "claimed_count >= 0 AND claimed_count <= quantity", name="tee_campaign_capacity"
        ),
    )
    op.create_table(
        "passport_tee_claims",
        sa.Column("id", BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column(
            "campaign_id",
            sa.String(50),
            sa.ForeignKey("passport_reward_campaigns.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            BIGINT(unsigned=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("allocation_no", sa.Integer(), nullable=False),
        sa.Column("size", sa.String(5), nullable=False),
        sa.Column("recipient_name", sa.String(100), nullable=False),
        sa.Column("phone_number", sa.String(11), nullable=False),
        sa.Column("postal_code", sa.String(5), nullable=False),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("address_detail", sa.String(200), nullable=False, server_default=""),
        sa.Column(
            "status",
            sa.Enum("requested", "preparing", "shipped", "completed", name="teeclaimstatus"),
            nullable=False,
            server_default="requested",
        ),
        sa.Column("consent_version", sa.String(50), nullable=False),
        sa.Column(
            "consented_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column("fulfilled_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("campaign_id", "user_id", name="tee_claim_member_unique"),
        sa.UniqueConstraint("campaign_id", "allocation_no", name="tee_claim_slot_unique"),
    )
    op.create_index("tee_claim_status_idx", "passport_tee_claims", ["status", "requested_at"])
    op.bulk_insert(
        campaigns,
        [
            {
                "id": "gsp-tee-2026",
                "required_stamps": 5,
                "quantity": 100,
                "claimed_count": 0,
                "is_open": True,
            }
        ],
    )


def downgrade():
    # Shipping data and allocation history must not be silently destroyed by rollback.
    raise RuntimeError(
        "Preserve tee applications and use an explicit data-retention rollback plan."
    )
