"""Add the Gangneung Olympic Museum official site."""

from alembic import op
from sqlalchemy import text

revision = "0022_gangneung_olympic_museum_site"
down_revision = "0021_remove_training_sites"
branch_labels = None
depends_on = None

EXTERNAL_ID = "3531540"
OFFICIAL_URL = "http://2018olympic.co.kr/"


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
