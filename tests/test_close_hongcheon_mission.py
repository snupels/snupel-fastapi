import importlib.util
from pathlib import Path

import sqlalchemy as sa


def test_closure_targets_only_linked_2026_mission_and_keeps_history():
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
    engine.dispose()
