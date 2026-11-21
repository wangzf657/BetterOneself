"""领域错误与 HTTP 映射（接口设计 §1：400/404/409/415/422/503）。"""

from __future__ import annotations


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, detail: str, *, retryable: bool = False) -> None:
        super().__init__(detail)
        self.detail = detail
        self.retryable = retryable


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class UnsupportedMedia(AppError):
    status_code = 415
    code = "unsupported_media"


class Validation(AppError):
    status_code = 422
    code = "validation"


class LLMError(AppError):
    """LLM 未配置或调用失败（503，带 retryable；B5-03）。"""

    status_code = 503
    code = "llm_error"


class LLMNotConfigured(LLMError):
    def __init__(self, detail: str = "尚未配置 AI 服务，请先到设置页填写") -> None:
        super().__init__(detail, retryable=False)


class LLMUnavailable(LLMError):
    def __init__(self, detail: str = "模型服务暂时不可用，请稍后重试") -> None:
        super().__init__(detail, retryable=True)
