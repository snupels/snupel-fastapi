from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migration_history_has_one_head():
    assert len(ScriptDirectory.from_config(Config("alembic.ini")).get_heads()) == 1
