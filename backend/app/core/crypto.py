"""密钥加密（B5-02、技术方案 §11）：Fernet 加密落库，密钥文件本机保存。"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_config


@lru_cache
def get_fernet() -> Fernet:
    path = get_config().secret_key_path
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(Fernet.generate_key())
    return Fernet(path.read_bytes())


def encrypt_secret(plain: str) -> str:
    return get_fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    return get_fernet().decrypt(token.encode("ascii")).decode("utf-8")


def try_decrypt(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return decrypt_secret(token)
    except InvalidToken:
        return None


def mask_secret(plain: str) -> str:
    """界面只显示掩码；掩码不是合法输入（提交掩码按未修改处理）。"""
    if len(plain) <= 8:
        return "****"
    return f"{plain[:3]}****{plain[-4:]}"
