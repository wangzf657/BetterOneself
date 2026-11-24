"""Alembic 迁移：V0.1 旧库升到 0002 后旧数据在、新列新表在；全新库升级不重复建。"""

from __future__ import annotations

import sqlalchemy as sa

NEW_COLUMNS = ("use_ai_planning", "planned_days", "learning_goal")


def _upgrade() -> sa.Engine:
    from app.core.config import get_config
    from app.core.db import make_engine
    from app.main import run_migrations

    run_migrations()
    return make_engine(f"sqlite:///{get_config().db_path.as_posix()}")


def _version(engine: sa.Engine) -> str:
    with engine.connect() as conn:
        return conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()


def test_upgrade_from_v01_db_keeps_data():
    from app.core.config import get_config
    from app.core.db import init_db, make_engine
    from app.models import DEFAULT_LEARNING_GOAL

    engine = make_engine(f"sqlite:///{get_config().db_path.as_posix()}")
    init_db(engine)
    # 造 V0.1 旧库：按当前模型建表后摘掉 V0.1.1 增量，版本停在 0001 并留一条旧数据
    with engine.begin() as conn:
        for name in NEW_COLUMNS:
            conn.execute(sa.text(f"ALTER TABLE studies DROP COLUMN {name}"))
        conn.execute(sa.text("DROP TABLE planning_proposals"))
        conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.execute(sa.text("INSERT INTO alembic_version VALUES ('0001')"))
        conn.execute(
            sa.text(
                "INSERT INTO studies (id, name, scheme, outline_status, created_at, updated_at)"
                " VALUES (1, '旧书', 'guided', 'ready', '2026-11-01', '2026-11-01')"
            )
        )

    engine = _upgrade()

    assert _version(engine) == "0002"
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT name, use_ai_planning, planned_days, learning_goal FROM studies")
        ).one()
        assert tuple(row) == ("旧书", 0, 10, DEFAULT_LEARNING_GOAL)
        assert sa.inspect(conn).has_table("planning_proposals")


def test_upgrade_fresh_db_is_idempotent():
    engine = _upgrade()
    engine = _upgrade()

    assert _version(engine) == "0002"
    with engine.connect() as conn:
        names = [c["name"] for c in sa.inspect(conn).get_columns("studies")]
        assert [names.count(c) for c in NEW_COLUMNS] == [1, 1, 1]
        assert sa.inspect(conn).has_table("planning_proposals")
