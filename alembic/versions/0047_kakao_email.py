"""Keep verified Kakao email separate from unique account identity."""
from alembic import op
import sqlalchemy as sa

revision = "0047_kakao_email"
down_revision = "0046_feed_deletion"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("kakao_email", sa.String(255), nullable=True))


def downgrade():
    op.drop_column("users", "kakao_email")
