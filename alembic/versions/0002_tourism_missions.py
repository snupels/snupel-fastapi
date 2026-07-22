"""Add tourism catalog and passport mission submissions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0002_tourism_missions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    activity_columns = {column["name"] for column in inspector.get_columns("activities")}
    op.execute(
        "ALTER TABLE activities MODIFY category "
        "ENUM('sports','event','festival','tourism') NOT NULL"
    )
    for column in (
        sa.Column("source", sa.String(50)),
        sa.Column("external_id", sa.String(100)),
        sa.Column("summary", sa.Text()),
        sa.Column("address", sa.String(500)),
        sa.Column("source_url", sa.Text()),
        sa.Column("starts_at", sa.DateTime()),
        sa.Column("ends_at", sa.DateTime()),
        sa.Column("metadata", mysql.JSON()),
        sa.Column("last_synced_at", sa.DateTime()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    ):
        if column.name not in activity_columns:
            op.add_column("activities", column)
    activity_indexes = {index["name"] for index in inspector.get_indexes("activities")}
    if "activities_source_external_unique" not in activity_indexes:
        op.create_index(
            "activities_source_external_unique",
            "activities",
            ["source", "external_id"],
            unique=True,
        )
    if "activities_source_synced_idx" not in activity_indexes:
        op.create_index(
            "activities_source_synced_idx", "activities", ["source", "last_synced_at"]
        )

    course_columns = {column["name"] for column in inspector.get_columns("courses")}
    if "title" not in course_columns:
        op.add_column("courses", sa.Column("title", sa.String(255)))
    if "description" not in course_columns:
        op.add_column("courses", sa.Column("description", sa.Text()))
    if "is_published" not in course_columns:
        op.add_column(
            "courses",
            sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )
    course_stamp_columns = {
        column["name"] for column in inspector.get_columns("course_stamps")
    }
    if "position" not in course_stamp_columns:
        op.add_column(
            "course_stamps",
            sa.Column("position", mysql.INTEGER(unsigned=True), nullable=False, server_default="0"),
        )

    if "stamp_submissions" in inspector.get_table_names():
        return
    op.create_table(
        "stamp_submissions",
        sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column("passport_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("stamp_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", name="submissionstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reviewer_id", mysql.BIGINT(unsigned=True)),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["passport_id"], ["passports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stamp_id"], ["stamps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("stamp_submissions_passport_idx", "stamp_submissions", ["passport_id"])
    op.create_index("stamp_submissions_status_idx", "stamp_submissions", ["status"])


def downgrade() -> None:
    op.drop_table("stamp_submissions")
    op.drop_column("course_stamps", "position")
    op.drop_column("courses", "is_published")
    op.drop_column("courses", "description")
    op.drop_column("courses", "title")
    op.drop_index("activities_source_synced_idx", table_name="activities")
    op.drop_index("activities_source_external_unique", table_name="activities")
    for name in (
        "is_active",
        "last_synced_at",
        "metadata",
        "ends_at",
        "starts_at",
        "source_url",
        "address",
        "summary",
        "external_id",
        "source",
    ):
        op.drop_column("activities", name)
    op.execute(
        "ALTER TABLE activities MODIFY category ENUM('sports','event','festival') NOT NULL"
    )
