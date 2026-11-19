"""Fernet 加密落库(M7-01):密钥存本机文件不入库(技术总纲 2.6)。"""

from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet

from app.config import get_config


@lru_cache
def _fernet() -> Fernet:
    key_path: Path = get_config().data_dir / "secret.key"
    if not key_path.exists():
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(Fernet.generate_key())
    return Fernet(key_path.read_bytes())


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
