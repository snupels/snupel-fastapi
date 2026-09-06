import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from scripts.repair_alembic_heads import redundant_revisions


def test_migration_history_has_one_head():
    assert len(ScriptDirectory.from_config(Config("alembic.ini")).get_heads()) == 1


def test_repair_removes_only_ancestors_that_overlap_newer_revisions():
    revisions = {
        "0015_pyeongchang_olympic_muse",
        "0016_feed_engagement",
        "0022_gangneung_olympic_museum",
        "0023_remove_kwandong_hockey_ce",
    }

    assert redundant_revisions(revisions) == {
        "0015_pyeongchang_olympic_muse",
        "0022_gangneung_olympic_museum",
    }


def test_pyeongchang_olympic_museum_mission_links_tourapi_activity(monkeypatch):
    migration_path = Path("alembic/versions/0015_pyeongchang_olympic_museum_mission.py")
    spec = importlib.util.spec_from_file_location("pyeongchang_mission_migration", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    statements = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    sql = "\n".join(str(statement) for statement in statements)
    parameters = {
        key: value.value
        for statement in statements
        for key, value in statement._bindparams.items()
    }
    assert len(statements) == 4
    assert "INSERT INTO courses" in sql
    assert "INSERT INTO course_stamps" in sql
    assert "stamp_catalog" in sql
    assert parameters["source"] == "tourapi"
    assert parameters["external_id"] == "2733036"
    assert parameters["title"] == migration.MISSION_TITLE


def test_feed_engagement_migration_creates_likes_and_comments(monkeypatch):
    migration_path = Path("alembic/versions/0016_feed_engagement.py")
    spec = importlib.util.spec_from_file_location("feed_engagement_migration", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    tables = []
    indexes = []
    monkeypatch.setattr(migration.op, "create_table", lambda name, *args, **kwargs: tables.append(name))
    monkeypatch.setattr(migration.op, "create_index", lambda name, *args, **kwargs: indexes.append(name))

    migration.upgrade()

    assert tables == ["feed_likes", "feed_comments"]
    assert indexes == ["feed_likes_submission_idx", "feed_comments_submission_idx"]


def test_hongcheon_marathon_uses_the_athletics_catalog_stamp():
    migration = Path("alembic/versions/0017_hongcheon_athletics.py").read_text(
        encoding="utf-8"
    )

    assert "region_ko = '홍천'" in migration
    assert "sport_en = 'ATHLETICS'" in migration
    assert "INSERT IGNORE INTO collected_stamps" in migration
    assert "UPDATE stamp_submissions" in migration
