"""学习项目、密钥与安全（B1、B5-02）：幂等、事务、三语义、掩码、日志无明文。"""

from __future__ import annotations

import logging

import pytest

from app.core.crypto import decrypt_secret, encrypt_secret, mask_secret
from app.core.errors import Conflict, UnsupportedMedia, Validation
from app.models import KnowledgePoint, Setting, Study
from app.services import app_settings, studies
from app.services.learning import get_or_create_session
from tests.conftest import BOOK, get_study


def test_create_idempotent_same_key(db) -> None:
    a, created_a = studies.create_study(
        db, name="书A", filename="a.txt", content=BOOK.encode(), idempotency_key="k1"
    )
    b, created_b = studies.create_study(
        db, name="书A", filename="a.txt", content=BOOK.encode(), idempotency_key="k1"
    )
    assert created_a and not created_b
    assert a.id == b.id  # 同 key 返回同一 study（P1-05）


def test_create_idempotent_concurrent_same_key(db) -> None:
    """BUG-003 回归（并发面）：并发同键请求只建一本书，输者幂等命中。"""
    import threading

    from app.core.db import get_session_local

    results: list[tuple[int, bool] | Exception] = []
    barrier = threading.Barrier(3)

    def worker() -> None:
        session = get_session_local()()
        try:
            barrier.wait()
            study, created = studies.create_study(
                session, name="并发书", filename="c.txt", content=BOOK.encode(),
                idempotency_key="kc",
            )
            results.append((study.id, created))
        except Exception as e:  # 胜负结果都要收集
            results.append(e)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ids = {r[0] for r in results if isinstance(r, tuple)}
    assert len(ids) == 1, f"并发同键应只建一本，实际 {ids}; errors={results}"
    rows = db.query(Study).filter_by(name="并发书").all()
    assert len(rows) == 1


def test_create_rejects_bad_files(db) -> None:
    with pytest.raises(UnsupportedMedia):
        studies.create_study(db, name="x", filename="a.docx", content=b"MZ....", idempotency_key=None)
    with pytest.raises(UnsupportedMedia):
        studies.create_study(db, name="x", filename="a.pdf", content=b"not pdf", idempotency_key=None)
    with pytest.raises(Validation):
        studies.create_study(db, name="x" * 201, filename="a.txt", content=BOOK.encode(), idempotency_key=None)


def test_delete_study_cascades_and_counts_impact(book) -> None:
    db = book
    study = get_study(db)
    leaf = db.query(KnowledgePoint).filter_by(name="1.1 什么是 Agent").one()
    get_or_create_session(db, study.id, leaf.id)
    impact = studies.delete_impact(db, study.id)
    assert impact["sessions"] == 1 and impact["notes"] == 0
    studies.delete_study(db, study.id)
    assert db.query(Study).count() == 0
    assert db.query(KnowledgePoint).count() == 0  # 级联清除


def test_replace_source_gates(book) -> None:
    db = book
    study = get_study(db)
    with pytest.raises(Conflict):  # 解析成功不可换文件
        studies.replace_source(db, study.id, filename="n.txt", content=BOOK.encode())


def test_secret_mask_and_fernet_roundtrip() -> None:
    token = encrypt_secret("sk-abcdef1234567890")
    assert decrypt_secret(token) == "sk-abcdef1234567890"
    assert mask_secret("sk-abcdef1234567890") == "sk-****7890"
    assert "sk-abcdef1234567890" not in mask_secret("sk-abcdef1234567890")


def test_settings_put_three_semantics(db) -> None:
    # 新值替换
    app_settings.put_settings(db, {"llm": {"base_url": "https://api.example.com/v1",
                                            "model": "gpt-x", "api_key": "sk-1111222233334444"}})
    got = app_settings.get_settings(db)
    assert got["llm"]["api_key"] == "sk-****4444"  # 掩码
    # 提交掩码 → 未修改
    app_settings.put_settings(db, {"llm": {"api_key": "sk-****4444"}})
    row = db.get(Setting, "llm.api_key")
    assert decrypt_secret(row.value or "") == "sk-1111222233334444"
    # 置 null → 清除
    app_settings.put_settings(db, {"llm": {"api_key": None}})
    assert db.get(Setting, "llm.api_key").value is None
    # 缺省 → 不变（model 仍在）
    assert db.get(Setting, "llm.model").value == "gpt-x"


def test_settings_bad_value_keeps_other_fields(db) -> None:
    app_settings.put_settings(db, {"llm": {"base_url": "https://a.com/v1"}})
    with pytest.raises(Validation):
        app_settings.put_settings(db, {"llm": {"base_url": "ftp://bad", "model": "m2"}})
    assert db.get(Setting, "llm.base_url").value == "https://a.com/v1"  # 失败不清空其他项


def test_no_plaintext_key_in_logs(db, caplog) -> None:
    from app.core.security import sanitize_error

    app_settings.put_settings(db, {"llm": {"api_key": "sk-SECRETKEY123456"}})
    with caplog.at_level(logging.DEBUG):
        err = RuntimeError("boom http://x with sk-SECRETKEY123456 and C:\\Users\\a\\k.txt")
        sanitized = sanitize_error(err)
        assert "sk-SECRETKEY123456" not in sanitized
        assert "C:\\Users" not in sanitized


def test_usage_written_per_scene(db) -> None:
    from app.core.llm import record_usage

    record_usage(db, "tutor", 100, 50)
    record_usage(db, "tutor", 30, 10)
    rows = app_settings.usage_between(db, None, None)
    row = next(r for r in rows if r["scene"] == "tutor")
    assert row["requests"] == 2 and row["prompt_tokens"] == 130


async def test_stub_complete_records_usage(db) -> None:
    """BUG-002 回归：桩模式 complete()（outline/quiz 场景）也要入账。"""
    from app.core.llm import complete

    await complete(db, [{"role": "user", "content": "hi"}], scene="outline")
    await complete(db, [{"role": "user", "content": "hi"}], scene="quiz")
    rows = {(r["scene"], r["requests"]) for r in app_settings.usage_between(db, None, None)}
    assert ("outline", 1) in rows and ("quiz", 1) in rows
