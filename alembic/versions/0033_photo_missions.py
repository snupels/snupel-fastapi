"""Add 24 photo missions using existing regional category stamps."""

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0033_photo_missions"
down_revision = "0032_jeongdongjin_railbike_site"
branch_labels = None
depends_on = None

MISSIONS = json.loads(
    (Path(__file__).parents[2] / "app/data/photo_missions.json").read_text(encoding="utf-8")
)


def upgrade() -> None:
    connection = op.get_bind()
    for mission in MISSIONS:
        activity = connection.execute(sa.text(
            "SELECT id, representative_image_url FROM activities "
            "WHERE source = :source AND external_id = :externalId AND is_active = 1"
        ), mission).mappings().one()
        stamp = connection.execute(sa.text(
            "SELECT s.id FROM stamps s JOIN stamp_catalog sc ON sc.id = s.stamp_catalog_id "
            "WHERE sc.region_ko = :region AND sc.sport_en = :sport"
        ), mission).scalar_one()
        conflict = connection.execute(sa.text(
            "SELECT c.id FROM course_stamps cs JOIN courses c ON c.id = cs.course_id "
            "WHERE cs.stamp_id = :stamp AND c.title <> :title LIMIT 1"
        ), {"stamp": stamp, "title": mission["title"]}).scalar_one_or_none()
        if conflict is not None:
            raise RuntimeError(f"Stamp already belongs to another mission: {mission['title']}")
        # Preserve catalog image and all existing collected/submission references.
        connection.execute(sa.text(
            "UPDATE stamps SET activity_id = :activity, description = :proof, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = :stamp"
        ), {"activity": activity["id"], "proof": mission["proof"], "stamp": stamp})
        connection.execute(sa.text(
            "INSERT INTO courses (category, sport_name, recommended_companion, "
            "representative_image_url, estimated_duration_minutes, theme, title, description, "
            "is_published, created_at, updated_at) "
            "SELECT 'event', :sport, '개인·친구·가족', :image, 60, 'stamp', :title, "
            ":description, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            "WHERE NOT EXISTS (SELECT 1 FROM courses WHERE title = :title)"
        ), {**mission, "image": activity["representative_image_url"]})
        connection.execute(sa.text(
            "INSERT INTO course_stamps (course_id, stamp_id, position, created_at) "
            "SELECT c.id, :stamp, 1, CURRENT_TIMESTAMP FROM courses c WHERE c.title = :title "
            "AND NOT EXISTS (SELECT 1 FROM course_stamps cs WHERE cs.course_id = c.id "
            "AND cs.stamp_id = :stamp)"
        ), {"stamp": stamp, "title": mission["title"]})


def downgrade() -> None:
    # Keep earned stamps and review history recoverable when unpublishing.
    for mission in MISSIONS:
        op.execute(sa.text("UPDATE courses SET is_published = 0 WHERE title = :title")
                   .bindparams(title=mission["title"]))
