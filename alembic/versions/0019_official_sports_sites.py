"""Add verified official sports facility URLs."""

from alembic import op
from sqlalchemy import text

revision = "0019_official_sports_sites"
down_revision = "0018_wolmyeong_site"
branch_labels = None
depends_on = None

OFFICIAL_URLS = {
    "1744974": "https://www.mullegil.com/mullegil/web/",
}


def upgrade() -> None:
    connection = op.get_bind()
    for external_id, url in OFFICIAL_URLS.items():
        connection.execute(
            text(
                "UPDATE activities SET source_url = :url, updated_at = CURRENT_TIMESTAMP "
                "WHERE source = 'tourapi' AND external_id = :external_id"
            ),
            {"external_id": external_id, "url": url},
        )


def downgrade() -> None:
    connection = op.get_bind()
    for external_id, url in OFFICIAL_URLS.items():
        connection.execute(
            text(
                "UPDATE activities SET source_url = NULL, updated_at = CURRENT_TIMESTAMP "
                "WHERE source = 'tourapi' AND external_id = :external_id AND source_url = :url"
            ),
            {"external_id": external_id, "url": url},
        )
