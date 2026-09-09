"""Shorten the exact seeded operator demo caption; preserve all engagement and flags."""
from alembic import op
import sqlalchemy as sa

revision = "0042_shorten_demo_caption"
down_revision = "0041_member_username"
branch_labels = None
depends_on = None

NEW_CAPTION = (
    "[운영자 데모] 강원 스포츠 피드에 오신 것을 환영합니다! "
    "좋아요와 댓글로 이야기를 나누고, 관심 있는 탐험가를 팔로우해 보세요."
)
OLD_CAPTION = NEW_CAPTION + " 이 게시글은 기능 체험용 안내이며 실제 방문·미션 인증이 아닙니다. 스탬프는 지급되지 않습니다."


def _replace(previous, replacement):
    op.get_bind().execute(sa.text(
        "UPDATE stamp_submissions SET feed_caption = :replacement, updated_at = CURRENT_TIMESTAMP "
        "WHERE is_demo = 1 AND object_key = :key AND feed_caption = :previous"
    ), {"replacement": replacement, "previous": previous, "key": "operator-community-demo-v1"})


def upgrade():
    _replace(OLD_CAPTION, NEW_CAPTION)


def downgrade():
    _replace(NEW_CAPTION, OLD_CAPTION)
