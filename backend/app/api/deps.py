"""API 依赖与异常处理。"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.db import get_session_local
from app.core.errors import AppError
from app.core.security import sanitize_error


def get_db() -> Iterator[Session]:
    db = get_session_local()()
    try:
        yield db
    finally:
        db.close()


async def app_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code, "retryable": exc.retryable},
        )
    return await unhandled_error_handler(_request, exc)


async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": f"内部错误：{sanitize_error(exc)}", "code": "internal", "retryable": True},
    )
