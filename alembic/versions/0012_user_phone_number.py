"""Add user phone number."""

import sqlalchemy as sa
from alembic import op

revision = "0012_user_phone_number"
down_revision = "0011_signup_consents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone_number", sa.String(length=11)))


def downgrade() -> None:
    op.drop_column("users", "phone_number")
