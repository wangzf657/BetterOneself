"""SQLite 引擎与会话:WAL + 外键 + sqlite-vec 扩展。连接监听器挂在 Engine 类上,测试库同样生效。"""

from collections.abc import Iterator
from datetime import UTC, datetime

import sqlite_vec
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session

VEC_CHUNKS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
  chunk_id INTEGER PRIMARY KEY,
  embedding float[1024]
)
"""


@event.listens_for(Engine, "connect")
def _tune_sqlite(dbapi_conn, _record) -> None:
    dbapi_conn.enable_load_extension(True)
    sqlite_vec.load(dbapi_conn)
    dbapi_conn.enable_load_extension(False)
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        from app.config import get_config

        _engine = create_engine(
            get_config().db_url, connect_args={"check_same_thread": False}
        )
    return _engine


def set_engine(engine: Engine) -> None:
    """测试注入专用:让 BackgroundTasks 等非请求路径也落在测试库上。"""
    global _engine
    _engine = engine


def create_all(engine: Engine) -> None:
    from app import models  # noqa: F401 注册全部模型

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(VEC_CHUNKS_DDL)


def get_db() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
