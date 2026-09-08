"""Register the 12 badge definitions without granting badges or editing proofs."""

import sqlalchemy as sa
from alembic import op

revision = "0038_mission_badge_catalog"
down_revision = "0037_user_features"
branch_labels = None
depends_on = None

# Keep this catalog frozen: applied migrations must not import mutable app data.
BADGES = (
    ("first_mission", "Challenge Starter · 미션 첫 완료"),
    ("first_mountain", "산악 입문자 · 산악 미션 첫 완료"),
    ("summit_1000m", "정상 정복자 · 해발 1,000m 이상 정상 방문 미션 완료"),
    ("trekking_three", "트레킹 러버 · 트레킹 미션 3개 완료"),
    ("first_marine", "Wave Rider · 해양 스포츠 미션 완료"),
    ("first_inland_water", "Water Adventurer · 내륙 수상 스포츠 미션 완료"),
    ("first_snow", "Snow Rookie · 설상 스포츠 미션 완료"),
    ("first_cycling", "Pedal Explorer · 자전거 미션 완료"),
    ("first_running", "Run Gangwon · 러닝 미션 완료"),
    ("three_missions", "강원 Explorer · 서로 다른 미션 3개 완료"),
    ("first_sunrise", "선라이즈 헌터 · 일출 명소 미션 완료"),
    ("three_sports", "Multi Sports Player · 서로 다른 스포츠 3종 미션 완료"),
)


def upgrade() -> None:
    connection = op.get_bind()
    existing = dict(connection.execute(sa.text("SELECT rule_key, id FROM badges WHERE rule_key IS NOT NULL")).all())
    # Preserve an existing Explorer badge ID and its earned records. If an
    # operator already registered both keys, do not merge/delete their records.
    if "three_regions" in existing and "three_missions" not in existing:
        connection.execute(sa.text(
            "UPDATE badges SET rule_key = 'three_missions', description = :description "
            "WHERE id = :id"
        ), {"description": BADGES[9][1], "id": existing["three_regions"]})
        existing["three_missions"] = existing["three_regions"]
    for rule_key, description in BADGES:
        if rule_key not in existing:
            connection.execute(sa.text(
                "INSERT INTO badges (rule_key, description, created_at, updated_at) "
                "VALUES (:rule_key, :description, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ), {"rule_key": rule_key, "description": description})
        elif rule_key in {"first_mountain", "three_missions"}:
            connection.execute(sa.text(
                "UPDATE badges SET description = :description WHERE rule_key = :rule_key"
            ), {"rule_key": rule_key, "description": description})


def downgrade() -> None:
    # Definitions may already be referenced by real earned badges. Retain them.
    pass
