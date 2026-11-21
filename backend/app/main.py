"""BetterOneself V0.1 后端入口。

启动时：Alembic 单个 init revision 建库 → 中断任务恢复 → 孤儿文件清理。
默认仅本机监听；单机单用户，无账号（技术方案 §11）。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from app.api.deps import app_error_handler, unhandled_error_handler
from app.api.knowledge import router as knowledge_router
from app.api.sessions import router as sessions_router
from app.api.settings import router as settings_router
from app.api.studies import router as studies_router
from app.api.studies import sources_router
from app.core.config import BACKEND_DIR, get_config
from app.core.errors import AppError
from app.core.security import OriginCheckMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def run_migrations() -> None:
    """空库起步：Alembic 单个 init revision（数据模型 §1）。"""
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{get_config().db_path.as_posix()}")
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    run_migrations()
    from app.services.pipeline import recover_on_startup

    recover_on_startup()
    yield


def _mount_frontend(app: FastAPI) -> None:
    dist = BACKEND_DIR.parent / "frontend" / "dist"
    if not dist.exists():
        return
    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        candidate = dist / full_path
        if full_path and candidate.is_file() and dist in candidate.resolve().parents:
            return FileResponse(str(candidate))
        return FileResponse(str(dist / "index.html"))


def create_app() -> FastAPI:
    app = FastAPI(title="BetterOneself", version="0.1.0", lifespan=lifespan)
    cfg = get_config()

    app.add_middleware(OriginCheckMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.allowed_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(studies_router, prefix="/api/studies")
    app.include_router(sources_router, prefix="/api")
    app.include_router(knowledge_router, prefix="/api")
    app.include_router(sessions_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")

    _mount_frontend(app)
    return app


app = create_app()
