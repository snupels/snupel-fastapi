import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.services.badge_rules import SPECIAL_BADGE_MISSIONS, earned_badge_rules


def migration():
    spec = importlib.util.spec_from_file_location("badge_photo_missions", Path("alembic/versions/0044_badge_photo_missions.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_special_badges_require_exact_verified_mission_and_api_identity():
    for identity, rule in SPECIAL_BADGE_MISSIONS.items():
        title, source, external_id = identity
        fact = dict(course_id=90, course_title=title, source=source, external_id=external_id)
        assert rule in earned_badge_rules([fact])
        assert rule not in earned_badge_rules([fact | {"course_title": "일반 방문"}])
        assert rule not in earned_badge_rules([fact | {"source": "manual"}])
        assert rule not in earned_badge_rules([fact | {"external_id": "other"}])
    assert not earned_badge_rules([])


def test_migration_preserves_stamps_is_idempotent_and_refuses_shared_stamps(monkeypatch):
    module = migration()
    assert {(m["title"], m["source"], m["externalId"]) for m in module.MISSIONS} == set(SPECIAL_BADGE_MISSIONS)
    with sa.create_engine("sqlite://").begin() as connection:
        for sql in [
            "CREATE TABLE activities (id INTEGER PRIMARY KEY, source TEXT, external_id TEXT, is_active INTEGER, representative_image_url TEXT)",
            "CREATE TABLE stamp_catalog (id INTEGER PRIMARY KEY, region_ko TEXT, sport_en TEXT)",
            "CREATE TABLE stamps (id INTEGER PRIMARY KEY, stamp_catalog_id INTEGER, activity_id INTEGER, description TEXT, image_url TEXT, updated_at TEXT)",
            "CREATE TABLE courses (id INTEGER PRIMARY KEY, category TEXT, sport_name TEXT, recommended_companion TEXT, representative_image_url TEXT, estimated_duration_minutes INTEGER, theme TEXT, title TEXT, description TEXT, participation_period TEXT, proof_instructions TEXT, photo_prompt TEXT, reward_description TEXT, steps TEXT, is_published INTEGER, created_at TEXT, updated_at TEXT)",
            "CREATE TABLE course_stamps (course_id INTEGER, stamp_id INTEGER, position INTEGER, created_at TEXT)",
        ]:
            connection.execute(sa.text(sql))
        for number, item in enumerate(module.MISSIONS, 1):
            params = item | {"id": number}
            connection.execute(sa.text("INSERT INTO activities VALUES (:id,:source,:externalId,1,'api.jpg')"), params)
            connection.execute(sa.text("INSERT INTO stamp_catalog VALUES (:id,:region,:sport)"), params)
            connection.execute(sa.text("INSERT INTO stamps VALUES (:id,:id,999,'old','catalog.svg',NULL)"), params)
        monkeypatch.setattr(module.op, "get_bind", lambda: connection)
        module.upgrade()
        module.upgrade()
        assert connection.scalar(sa.text("SELECT COUNT(*) FROM courses")) == 2
        assert connection.scalar(sa.text("SELECT COUNT(*) FROM course_stamps")) == 2
        assert connection.scalar(sa.text("SELECT COUNT(*) FROM stamps WHERE image_url='catalog.svg'")) == 2
        assert connection.scalar(sa.text("SELECT COUNT(*) FROM courses WHERE proof_instructions IS NOT NULL AND is_published=1")) == 2
        module.downgrade()
        assert connection.scalar(sa.text("SELECT COUNT(*) FROM course_stamps")) == 2
        connection.execute(sa.text("UPDATE courses SET title='다른 미션' WHERE id=1"))
        with pytest.raises(RuntimeError, match="another mission"):
            module.upgrade()
