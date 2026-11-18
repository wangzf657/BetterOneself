"""测试夹具:临时 SQLite(含 vec 虚拟表)+ 覆盖 get_db 与全局引擎。"""

import os

# 测试一律 stub LLM/embedding,不花真 token(硬性约定 5)
os.environ.setdefault("BO_STUB_LLM", "1")

import pytest  # noqa: E402
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app import db as app_db
from app import main
from app.db import create_all


@pytest.fixture
def engine(tmp_path) -> Engine:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    create_all(engine)
    app_db.set_engine(engine)
    yield engine
    engine.dispose()
    app_db.set_engine(None)


@pytest.fixture
def db(engine: Engine) -> Session:
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(engine: Engine) -> TestClient:
    def override_get_db():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[app_db.get_db] = override_get_db
    # 不进 context:跳过 lifespan(启动迁移),测试库由 create_all 自建
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()
