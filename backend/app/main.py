"""FastAPI 装配。"""

from contextlib import asynccontextmanager

from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alembic import command
from app.api import cards, knowledge, kps, plans, quizzes, sessions, sources, studies, today
from app.config import BACKEND_DIR


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.config import get_config

    if get_config().reset_db:
        import shutil

        shutil.rmtree(get_config().data_dir, ignore_errors=True)
        get_config().uploads_dir.mkdir(parents=True, exist_ok=True)  # get_config 已缓存,需手动重建
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
app.include_router(quizzes.router)
app.include_router(cards.router)
app.include_router(kps.router)
app.include_router(plans.router)
app.include_router(today.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/dev/fake-today")
def set_fake_today(payload: dict) -> dict:
    """E2E 时间快进:改 fake_today 并重建配置。仅 stub 模式开放(误用防护)。"""
    import os

    from app.config import get_config

    if not get_config().stub_llm:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="仅测试模式可用")
    date = payload.get("date")
    if date:
        os.environ["BO_FAKE_TODAY"] = str(date)
    else:
        os.environ.pop("BO_FAKE_TODAY", None)
    get_config.cache_clear()
    return {"fake_today": os.environ.get("BO_FAKE_TODAY")}
