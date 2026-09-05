import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migration_history_has_one_head():
    assert len(ScriptDirectory.from_config(Config("alembic.ini")).get_heads()) == 1


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
