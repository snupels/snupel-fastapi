"""Create missing passports and connect stamps to the catalog."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0008_stampbook"
down_revision = "0007_course_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO passports (user_id)
            SELECT users.id
            FROM users
            LEFT JOIN passports ON passports.user_id = users.id
            WHERE passports.id IS NULL
            """
        )
    )
    op.add_column(
        "stamps",
        sa.Column("stamp_catalog_id", mysql.BIGINT(unsigned=True), nullable=True),
    )
    op.create_foreign_key(
        "stamps_stamp_catalog_fk",
        "stamps",
        "stamp_catalog",
        ["stamp_catalog_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "stamps_stamp_catalog_unique",
        "stamps",
        ["stamp_catalog_id"],
    )


def downgrade() -> None:
    op.drop_constraint("stamps_stamp_catalog_unique", "stamps", type_="unique")
    op.drop_constraint("stamps_stamp_catalog_fk", "stamps", type_="foreignkey")
    op.drop_column("stamps", "stamp_catalog_id")
