"""Add optional private member address fields without changing existing users."""

import sqlalchemy as sa
from alembic import op

revision = "0040_member_address"
down_revision = "0039_public_sports_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("postal_code", sa.String(5), nullable=True))
    op.add_column("users", sa.Column("address", sa.String(500), nullable=True))
    op.add_column("users", sa.Column("address_detail", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "address_detail")
    op.drop_column("users", "address")
    op.drop_column("users", "postal_code")
