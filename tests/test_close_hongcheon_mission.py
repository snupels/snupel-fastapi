import importlib.util
from pathlib import Path

import sqlalchemy as sa


def test_closure_and_reopening_target_only_linked_mission_and_keep_history(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "closure", Path("alembic/versions/0050_close_hongcheon_mission.py")
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        for sql in (
            "CREATE TABLE courses (id INTEGER PRIMARY KEY, title TEXT, category TEXT, is_closed BOOLEAN DEFAULT 0, is_published BOOLEAN DEFAULT 1, participation_period TEXT)",
            "CREATE TABLE activities (id INTEGER PRIMARY KEY, external_id TEXT)",
            "CREATE TABLE stamps (id INTEGER PRIMARY KEY, activity_id INTEGER)",
            "CREATE TABLE course_stamps (course_id INTEGER, stamp_id INTEGER)",
            "CREATE TABLE collected_stamps (id INTEGER PRIMARY KEY, stamp_id INTEGER)",
        ):
            connection.execute(sa.text(sql))
        connection.execute(sa.text("INSERT INTO courses (id, title, category) VALUES (:id,:title,:category)"), [
            {"id": 1, "title": migration.MISSION_TITLE, "category": "event"},
            {"id": 2, "title": migration.MISSION_TITLE, "category": "event"},
            {"id": 3, "title": "다른 미션", "category": "event"},
        ])
        connection.execute(sa.text("INSERT INTO activities VALUES (1,:external_id)"),
                           {"external_id": migration.EVENT_EXTERNAL_ID})
        connection.execute(sa.text("INSERT INTO stamps VALUES (1,1)"))
        connection.execute(sa.text("INSERT INTO course_stamps VALUES (1,1),(3,1)"))
        connection.execute(sa.text("INSERT INTO collected_stamps VALUES (1,1)"))
        migration._close_mission(connection)
        migration._close_mission(connection)
        assert connection.execute(sa.text("SELECT id,is_closed,is_published,participation_period FROM courses ORDER BY id")).all() == [
            (1, 1, 1, "2026.10.04 마감"), (2, 0, 1, None), (3, 0, 1, None),
        ]
        assert connection.scalar(sa.text("SELECT COUNT(*) FROM collected_stamps")) == 1
        assert connection.scalar(sa.text("SELECT COUNT(*) FROM course_stamps")) == 2
        reopen_spec = importlib.util.spec_from_file_location(
            "reopening", Path("alembic/versions/0051_reopen_hongcheon_mission.py")
        )
        reopening = importlib.util.module_from_spec(reopen_spec)
        reopen_spec.loader.exec_module(reopening)
        monkeypatch.setattr(reopening.op, "get_bind", lambda: connection)
        # An unrelated closed mission must remain closed.
        connection.execute(sa.text("UPDATE courses SET is_closed=1 WHERE id=3"))
        reopening.upgrade()
        reopening.upgrade()
        reopening.downgrade()
        assert connection.execute(sa.text("SELECT id,is_closed,is_published FROM courses ORDER BY id")).all() == [
            (1, 0, 1), (2, 0, 1), (3, 1, 1),
        ]
        assert "행사 종료 후에도" in connection.scalar(sa.text("SELECT participation_period FROM courses WHERE id=1"))
        assert connection.scalar(sa.text("SELECT COUNT(*) FROM collected_stamps")) == 1
        assert connection.scalar(sa.text("SELECT COUNT(*) FROM course_stamps")) == 2
    engine.dispose()
