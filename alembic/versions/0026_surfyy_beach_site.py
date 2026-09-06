"""Add the Surfyy Beach official site."""

from alembic import op
from sqlalchemy import text

revision = "0026_surfyy_beach_site"
down_revision = "0025_lepovalley_site"
branch_labels = None
depends_on = None

EXTERNAL_ID = "2501905"
OFFICIAL_URL = "https://www.surfyy.com/"


def upgrade() -> None:
    op.get_bind().execute(
        text(
            "UPDATE activities SET source_url = :url, updated_at = CURRENT_TIMESTAMP "
            "WHERE source = 'tourapi' AND external_id = :external_id"
        ),
        {"external_id": EXTERNAL_ID, "url": OFFICIAL_URL},
    )


def downgrade() -> None:
    op.get_bind().execute(
        text(
            "UPDATE activities SET source_url = NULL, updated_at = CURRENT_TIMESTAMP "
            "WHERE source = 'tourapi' AND external_id = :external_id AND source_url = :url"
        ),
        {"external_id": EXTERNAL_ID, "url": OFFICIAL_URL},
    )
