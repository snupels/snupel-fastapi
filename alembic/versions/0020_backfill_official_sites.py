"""Backfill verified official sports facility URLs."""

from alembic import op
from sqlalchemy import text

from app.jobs.sync_tourism import OFFICIAL_SPORT_URLS

revision = "0020_backfill_official_sites"
down_revision = "0019_official_sports_sites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    for external_id, url in OFFICIAL_SPORT_URLS.items():
        connection.execute(
            text(
                "UPDATE activities SET source_url = :url, updated_at = CURRENT_TIMESTAMP "
                "WHERE source = 'tourapi' AND external_id = :external_id"
            ),
            {"external_id": external_id, "url": url},
        )


def downgrade() -> None:
    connection = op.get_bind()
    for external_id, url in OFFICIAL_SPORT_URLS.items():
        connection.execute(
            text(
                "UPDATE activities SET source_url = NULL, updated_at = CURRENT_TIMESTAMP "
                "WHERE source = 'tourapi' AND external_id = :external_id AND source_url = :url"
            ),
            {"external_id": external_id, "url": url},
        )
