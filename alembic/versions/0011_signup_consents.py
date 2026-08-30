"""Add signup consent records."""

import sqlalchemy as sa
from alembic import op

revision = "0011_signup_consents"
down_revision = "0010_user_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("terms_agreed_at", sa.DateTime()))
    op.add_column("users", sa.Column("privacy_agreed_at", sa.DateTime()))
    op.add_column(
        "users",
        sa.Column(
            "marketing_email_agreed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "marketing_sns_agreed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "marketing_sns_agreed")
    op.drop_column("users", "marketing_email_agreed")
    op.drop_column("users", "privacy_agreed_at")
    op.drop_column("users", "terms_agreed_at")
