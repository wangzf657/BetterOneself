"""数据库引擎与建库（数据模型 §1、§8）。

- 每连接启用 PRAGMA foreign_keys=ON，并用真实 SQLite 集成测试验证，不依赖模型声明；
- vec_chunks 为 sqlite-vec 虚表（bge-m3，1024 维 float32），chunk_id 为主键；
- 空库起步：Alembic 单个 init revision 建全部表与虚表；测试直接调用 init_db 走同一代码路径。
"""

from __future__ import annotations

from typing import Any

import sqlite_vec
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_config
from app.models import Base

EMBED_DIM = 1024


def _on_connect(dbapi_conn: object, _record: object) -> None:
    import sqlite3

    assert isinstance(dbapi_conn, sqlite3.Connection)
    dbapi_conn.execute("PRAGMA foreign_keys=ON")
    dbapi_conn.enable_load_extension(True)
    sqlite_vec.load(dbapi_conn)
    dbapi_conn.enable_load_extension(False)


def make_engine(url: str, *, static_pool: bool = False) -> Engine:
    connect_args = {"check_same_thread": False}
    extra_kwargs: dict[str, Any] = {}
    if static_pool:
        from sqlalchemy.pool import StaticPool

        extra_kwargs["poolclass"] = StaticPool
    engine = create_engine(url, connect_args=connect_args, **extra_kwargs)
    event.listen(engine, "connect", _on_connect)
    return engine


def get_engine() -> Engine:
    return make_engine(f"sqlite:///{get_config().db_path}")


_engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def get_session_local() -> sessionmaker[Session]:
    global _engine, SessionLocal
    if SessionLocal is None:
        if _engine is None:
            _engine = get_engine()
        SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return SessionLocal


def init_db(bind: Engine | Connection) -> None:
    """建全部表 + sqlite-vec 虚表（Alembic init revision 与测试共用）。"""
    ddl = text(
        "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks "
        "USING vec0(chunk_id INTEGER PRIMARY KEY, embedding float[1024])"
    )
    Base.metadata.create_all(bind)
    if isinstance(bind, Connection):
        bind.execute(ddl)
    else:
        with bind.begin() as conn:
            conn.execute(ddl)
