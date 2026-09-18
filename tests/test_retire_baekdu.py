import importlib.util
from pathlib import Path
from unittest.mock import Mock


def test_retirement_is_scoped_and_preserves_records(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "retirement", root / "alembic/versions/0045_retire_baekdu.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    connection = Mock()
    monkeypatch.setattr(module.op, "get_bind", lambda: connection)
    module.upgrade()
    sql = str(connection.execute.call_args.args[0])
    assert "source = 'forest_baekdu'" in sql
    assert "is_active = 0" in sql and "DELETE" not in sql
    for identifier in ("BAEK_34", "BAEK_36", "BAEK_37", "BAEK_38"):
        assert identifier in sql
    source = (root / "app/jobs/sync_tourism.py").read_text(encoding="utf-8")
    assert "sync_baekdu" not in source
