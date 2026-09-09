"""Create one clearly labelled, non-reward demo under the configured operator."""
import sqlalchemy as sa

DEMO_KEY = "operator-community-demo-v1"
CAPTION = (
    "[운영자 데모] 강원 스포츠 피드에 오신 것을 환영합니다! "
    "좋아요와 댓글로 이야기를 나누고, 관심 있는 탐험가를 팔로우해 보세요."
)


def seed_demo(connection, admin_emails):
    existing = connection.execute(sa.text(
        "SELECT id FROM stamp_submissions WHERE object_key = :key AND is_demo = 1"
    ), {"key": DEMO_KEY}).scalar_one_or_none()
    if existing is not None:
        return "already_exists"
    if not admin_emails:
        return "no_configured_operator"
    users = connection.execute(sa.text(
        "SELECT id FROM users WHERE LOWER(email) IN :emails"
    ).bindparams(sa.bindparam("emails", expanding=True)), {"emails": sorted(admin_emails)}).scalars().all()
    if len(users) != 1:
        return "operator_selection_required"
    connection.execute(sa.text(
        "INSERT INTO stamp_submissions "
        "(passport_id, stamp_id, author_id, is_demo, object_key, share_to_feed, feed_caption, "
        "status, reviewer_id, reviewed_at, created_at, updated_at) "
        "VALUES (NULL, NULL, :author, 1, :key, 1, :caption, 'approved', :author, "
        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    ), {"author": users[0], "key": DEMO_KEY, "caption": CAPTION})
    return "created"
