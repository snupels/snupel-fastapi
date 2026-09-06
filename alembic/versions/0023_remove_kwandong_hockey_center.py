"""Remove the university-affiliated Kwandong hockey center."""

from alembic import op
from sqlalchemy import text

revision = "0023_remove_kwandong_hockey_center"
down_revision = "0022_gangneung_olympic_museum_site"
branch_labels = None
depends_on = None

EXTERNAL_ID = "2534281"


def upgrade() -> None:
    op.get_bind().execute(
        text(
            "UPDATE activities SET is_active = 0, updated_at = CURRENT_TIMESTAMP "
            "WHERE source = 'tourapi' AND external_id = :external_id"
        ),
        {"external_id": EXTERNAL_ID},
    )


def downgrade() -> None:
    op.get_bind().execute(
        text(
            "UPDATE activities SET is_active = 1, updated_at = CURRENT_TIMESTAMP "
            "WHERE source = 'tourapi' AND external_id = :external_id"
        ),
        {"external_id": EXTERNAL_ID},
    )
