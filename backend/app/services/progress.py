"""导入/拆解进度(内存态,M1-06):解析/向量化/拆解各阶段的批次计数,前端轮询展示。

进程内单副本即可:后台任务与 API 同进程(单机自用);
写库会与解析的长事务抢 SQLite 单写者锁,故不落库。
shortcut: 多 worker/队列化部署时升级为任务队列携带进度。
"""

import time
from typing import Any

_progress: dict[str, dict[str, Any]] = {}


def set(key: str, stage: str, current: int = 0, total: int | None = None) -> None:
    _progress[key] = {
        "stage": stage,
        "current": current,
        "total": total,
        "updated_at": time.time(),
    }


def clear(key: str) -> None:
    _progress.pop(key, None)


def get(keys: list[str]) -> list[dict[str, Any]]:
    return [_progress[k] | {"key": k} for k in keys if k in _progress]
