"""环境配置。开发期直读 backend/.env(技术总纲 2.6);里程碑 5 设置页上线后由库内配置覆盖。"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_prefix="BO_", extra="ignore"
    )

    data_dir: Path = BACKEND_DIR / "data"
    uploads_dir: Path = BACKEND_DIR / "data" / "uploads"

    llm_base_url: str = "https://open.bigmodel.cn/api/coding/paas/v4"
    llm_api_key: str = ""
    llm_model: str = "glm-5.3-flash"
    embed_base_url: str = "https://api.siliconflow.cn/v1"
    embed_api_key: str = ""
    embed_model: str = "BAAI/bge-m3"

    # 测试开关:以确定性 stub 替代真实 LLM/embedding,E2E 不花真 token
    stub_llm: bool = False
    # E2E 时间跳跃:模拟"今天"的 ISO 日期
    fake_today: str | None = None

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'app.db'}"


@lru_cache
def get_config() -> Config:
    cfg = Config()
    cfg.uploads_dir.mkdir(parents=True, exist_ok=True)
    return cfg
