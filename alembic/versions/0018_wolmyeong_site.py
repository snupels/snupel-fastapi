"""Add the Wolmyeong fishing site URL."""

import sqlalchemy as sa
from alembic import op

revision = "0018_wolmyeong_site"
down_revision = "0017_hongcheon_athletics"
branch_labels = None
depends_on = None

SOURCE = "tourapi"
EXTERNAL_ID = "2702189"
OFFICIAL_URL = "https://www.wolmyeong.com/"


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE activities SET source_url = :url, updated_at = CURRENT_TIMESTAMP "
            "WHERE source = :source AND external_id = :external_id"
        ).bindparams(url=OFFICIAL_URL, source=SOURCE, external_id=EXTERNAL_ID)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE activities SET source_url = NULL, updated_at = CURRENT_TIMESTAMP "
            "WHERE source = :source AND external_id = :external_id AND source_url = :url"
        ).bindparams(url=OFFICIAL_URL, source=SOURCE, external_id=EXTERNAL_ID)
    )
