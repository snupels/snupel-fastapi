"""Keep the original cover proof and allow four additional proof photos."""
import sqlalchemy as sa
from alembic import op

revision = "0043_submission_photos"
down_revision = "0042_shorten_demo_caption"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("stamp_submissions", sa.Column("extra_object_keys", sa.JSON(), nullable=True))


def downgrade():
    # Retain submitted evidence; old applications safely ignore this column.
    pass
