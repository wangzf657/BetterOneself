"""应用配置：单机自用，默认仅本机监听（技术方案 §11）。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BO_", env_file=None)

    # 运行数据目录：SQLite、上传文件、加密密钥（.gitignore 已忽略 backend/data/）
    data_dir: Path = BACKEND_DIR / "data"
    host: str = "127.0.0.1"
    port: int = 8000

    # 上传边界（P1-06）
    max_upload_bytes: int = 300 * 1024 * 1024
    max_pdf_pages: int = 2000
    max_epub_entries: int = 4000
    max_epub_uncompressed: int = 600 * 1024 * 1024

    # 允许的前端来源（本机开发服务器 + 生产同源），CORS/Origin 校验用
    extra_allowed_origins: str = ""

    # E2E/开发桩：1 = 用确定性桩客户端替代真实 LLM，不触网（测试纪律）
    llm_stub: bool = False

    @property
    def db_path(self) -> Path:
        return self.data_dir / "betteroneself.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def secret_key_path(self) -> Path:
        return self.data_dir / "secret.key"

    def allowed_origins(self) -> list[str]:
        origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
        origins += [o.strip() for o in self.extra_allowed_origins.split(",") if o.strip()]
        return origins


@lru_cache
def get_config() -> AppConfig:
    cfg = AppConfig()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.uploads_dir.mkdir(parents=True, exist_ok=True)
    return cfg
