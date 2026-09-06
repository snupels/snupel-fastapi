"""Update the Jeongdongjin Rail Bike official site."""

from alembic import op
from sqlalchemy import text

revision = "0032_jeongdongjin_railbike_site"
down_revision = "0031_beavers_dock_site"
branch_labels = None
depends_on = None

EXTERNAL_ID = "2396259"
OLD_URL = "http://www.sunbike.kr/"
OFFICIAL_URL = "https://www.railtrip.co.kr/homepage/jeongdongjin/"


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
            "UPDATE activities SET source_url = :old_url, updated_at = CURRENT_TIMESTAMP "
            "WHERE source = 'tourapi' AND external_id = :external_id AND source_url = :url"
        ),
        {"external_id": EXTERNAL_ID, "old_url": OLD_URL, "url": OFFICIAL_URL},
    )
