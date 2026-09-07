"""Unpublish manually entered routes: hiking must come from upstream APIs."""

import sqlalchemy as sa
from alembic import op

revision = "0035_remove_curated_hiking"
down_revision = "0034_verified_hiking"
branch_labels = None
depends_on = None

KEYS = (
    "verified-hiking-odae-birobong", "verified-hiking-odae-sangwangbong",
    "verified-hiking-odae-dongdaesan", "verified-hiking-odae-durobong",
    "verified-hiking-gyebangsan-course-1",
)


def upgrade() -> None:
    for key in KEYS:
        op.get_bind().execute(sa.text(
            "UPDATE activities SET is_active = 0, updated_at = CURRENT_TIMESTAMP "
            "WHERE source IS NULL AND external_id = :key"
        ), {"key": key})


def downgrade() -> None:
    # Do not silently republish data the operator explicitly rejected.
    pass
