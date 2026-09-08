"""Add unique optional usernames without assigning or changing existing users."""

import sqlalchemy as sa
from alembic import op

revision = "0041_member_username"
down_revision = "0040_member_address"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(20), nullable=True))
    op.create_unique_constraint("users_username_unique", "users", ["username"])


def downgrade() -> None:
    op.drop_constraint("users_username_unique", "users", type_="unique")
    op.drop_column("users", "username")
