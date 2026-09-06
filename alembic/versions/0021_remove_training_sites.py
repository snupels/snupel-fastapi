"""Remove non-sports training facilities from public activities."""

from alembic import op
from sqlalchemy import text

revision = "0021_remove_training_sites"
down_revision = "0020_backfill_official_sites"
branch_labels = None
depends_on = None

EXTERNAL_IDS = ("131167", "131169", "131471")


def upgrade() -> None:
    connection = op.get_bind()
    for external_id in EXTERNAL_IDS:
        connection.execute(
            text(
                "UPDATE activities SET is_active = 0, updated_at = CURRENT_TIMESTAMP "
                "WHERE source = 'tourapi' AND external_id = :external_id"
            ),
            {"external_id": external_id},
        )


def downgrade() -> None:
    connection = op.get_bind()
    for external_id in EXTERNAL_IDS:
        connection.execute(
            text(
                "UPDATE activities SET is_active = 1, updated_at = CURRENT_TIMESTAMP "
                "WHERE source = 'tourapi' AND external_id = :external_id"
            ),
            {"external_id": external_id},
        )
