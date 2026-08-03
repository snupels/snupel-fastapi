"""Store the Gangwon passport stamp catalog."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0003_stamp_catalog"
down_revision = "0002_tourism_missions"
branch_labels = None
depends_on = None

REGIONS = (
    ("춘천", "CHUNCHEON", "chuncheon"), ("원주", "WONJU", "wonju"),
    ("강릉", "GANGNEUNG", "gangneung"), ("동해", "DONGHAE", "donghae"),
    ("태백", "TAEBAEK", "taebaek"), ("속초", "SOKCHO", "sokcho"),
    ("삼척", "SAMCHEOK", "samcheok"), ("홍천", "HONGCHEON", "hongcheon"),
    ("횡성", "HOENGSEONG", "hoengseong"), ("영월", "YEONGWOL", "yeongwol"),
    ("평창", "PYEONGCHANG", "pyeongchang"), ("정선", "JEONGSEON", "jeongseon"),
    ("철원", "CHEORWON", "cheorwon"), ("화천", "HWACHEON", "hwacheon"),
    ("양구", "YANGGU", "yanggu"), ("인제", "INJE", "inje"),
    ("고성", "GOSEONG", "goseong"), ("양양", "YANGYANG", "yangyang"),
)
SPORTS = (
    ("산악", "MOUNTAIN", "mountain", "#2F6B4F"), ("수상", "WATER", "water", "#2E78B7"),
    ("설상", "SNOW", "snow", "#5C9FCB"), ("올림픽", "OLYMPIC", "olympic", "#7A58A6"),
    ("육상", "ATHLETICS", "athletics", "#B94E32"),
)


def upgrade() -> None:
    if "stamp_catalog" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "stamp_catalog",
            sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
            sa.Column("region_ko", sa.String(30), nullable=False),
            sa.Column("region_en", sa.String(30), nullable=False),
            sa.Column("sport_ko", sa.String(30), nullable=False),
            sa.Column("sport_en", sa.String(30), nullable=False),
            sa.Column("color", sa.String(7), nullable=False),
            sa.Column("image_key", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("region_en", "sport_en", name="stamp_catalog_region_sport_unique"),
        )
    op.bulk_insert(
        sa.table("stamp_catalog", sa.column("region_ko"), sa.column("region_en"), sa.column("sport_ko"), sa.column("sport_en"), sa.column("color"), sa.column("image_key")),
        [
            {
                "region_ko": region_ko, "region_en": region_en, "sport_ko": sport_ko,
                "sport_en": sport_en, "color": color,
                "image_key": f"stamps/{number:02d}-{region_slug}-{sport_slug}.svg",
            }
            for number, (region_ko, region_en, region_slug) in enumerate(REGIONS, 1)
            for offset, (sport_ko, sport_en, sport_slug, color) in enumerate(SPORTS)
            for number in (number * 5 + offset,)
        ],
    )


def downgrade() -> None:
    op.drop_table("stamp_catalog")
