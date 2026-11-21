"""测试夹具：临时数据目录 + 内存库 + 桩 LLM（BO_LLM_STUB，不触网、不花 token）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    """每个测试独立数据目录 + 桩 LLM。"""
    monkeypatch.setenv("BO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BO_LLM_STUB", "1")
    os.environ.pop("BO_EXTRA_ALLOWED_ORIGINS", None)

    import app.core.config as config_mod

    config_mod.get_config.cache_clear()
    cfg = config_mod.get_config()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.uploads_dir.mkdir(parents=True, exist_ok=True)

    # 临时文件库（TestClient 线程池与服务代码并发访问，内存 StaticPool 会跨线程踩连接）
    import app.core.db as dbmod
    from app.core.db import init_db, make_engine

    engine = make_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    init_db(engine)
    monkeypatch.setattr(dbmod, "_engine", engine)
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(dbmod, "SessionLocal", session_factory)
    yield
    config_mod.get_config.cache_clear()


@pytest.fixture
def db():
    import app.core.db as dbmod

    session = dbmod.get_session_local()()
    yield session
    session.rollback()
    session.close()


BOOK = """第一章 Agent 导论

Agent 是能够感知环境、做出决策并执行动作的系统。本章介绍基本组成与运行循环。

1.1 什么是 Agent

Agent 的核心是决策循环：观察、思考、行动。信息筛选的目标是保留与当前任务直接相关的证据，而不是收集得越多越好。

1.2 Agent 的组成

Agent 通常由感知、记忆、规划与执行模块组成。

第二章 上下文工程

上下文窗口并不是越长越好。压缩不是简单缩短文字，而是降低无关信息对注意力的干扰。

2.1 信息筛选

筛选标准有三条：任务相关性、时效性与可信度。

2.2 信息压缩

压缩的本质是取舍：优先保留结论与关键证据。

第三章 附录 习题答案

这里是各章习题的参考答案，不是学习内容。
"""


def make_book_db(db, *, name: str = "测试书", content: str = BOOK, filename: str = "b.txt"):
    """建书并跑完阶段 A/B（不触发后续 followups）。"""
    from app.services import pipeline
    from app.services.studies import create_study

    study, _ = create_study(db, name=name, filename=filename, content=content.encode("utf-8"),
                            idempotency_key=None)
    assert study.primary_source_id is not None
    pipeline.run_parse(study.primary_source_id)
    db.expire_all()
    return study


@pytest.fixture
def book(db):
    make_book_db(db)
    return db


def get_study(db):
    from app.models import Study

    return db.query(Study).order_by(Study.id).first()
