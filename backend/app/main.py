"""FastAPI 装配。"""

from contextlib import asynccontextmanager

from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alembic import command
from app.api import knowledge, sessions, sources, studies
from app.config import BACKEND_DIR


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 启动即迁到最新,单机自用免手工步骤;已在 head 时为空操作
    cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    yield


app = FastAPI(title="BetterOneself", lifespan=lifespan)

# 单机自用;开发期 Vite 端口
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(studies.router)
app.include_router(sources.router)
app.include_router(knowledge.router)
app.include_router(sessions.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
