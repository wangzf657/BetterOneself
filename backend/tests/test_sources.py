"""M1-02/06:上传→后台解析→切片入库→状态可查;失败给明确错误。"""

import io
from pathlib import Path

from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Source

MD_CONTENT = "# 所有权\nRust 的核心概念。\n\n## 移动语义\n赋值即移动。\n\n## 借用\n引用不拥有值。\n"


def _upload(client, study_id, name, content):
    return client.post(
        f"/api/studies/{study_id}/sources",
        files={"file": (name, io.BytesIO(content.encode()), "text/markdown")},
    )


def test_upload_md_parses_to_ready_with_chunks(client):
    study = client.post("/api/studies", json={"name": "Rust", "goal": "学会"}).json()

    resp = _upload(client, study["id"], "rust-notes.md", MD_CONTENT)
    assert resp.status_code == 201
    source = resp.json()
    assert source["type"] == "md"

    # TestClient 在响应后同步执行后台任务
    detail = client.get(f"/api/sources/{source['id']}").json()
    assert detail["parse_status"] == "ready"
    assert [c["heading_path"] for c in detail["chunks"]] == [
        "所有权",
        "所有权 > 移动语义",
        "所有权 > 借用",
    ]
    assert detail["chunks"][0]["content"].startswith("# 所有权")


def test_upload_rejects_unsupported_type(client):
    study = client.post("/api/studies", json={"name": "Rust", "goal": "g"}).json()
    resp = client.post(
        f"/api/studies/{study['id']}/sources",
        files={"file": ("virus.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert resp.status_code == 415


def test_list_sources_scoped_to_study(client):
    s1 = client.post("/api/studies", json={"name": "A", "goal": "a"}).json()
    s2 = client.post("/api/studies", json={"name": "B", "goal": "b"}).json()
    _upload(client, s1["id"], "one.md", "# 一\n内容")

    assert len(client.get(f"/api/studies/{s1['id']}/sources").json()) == 1
    assert client.get(f"/api/studies/{s2['id']}/sources").json() == []


def test_reparse_replaces_chunks(client):
    study = client.post("/api/studies", json={"name": "Rust", "goal": "g"}).json()
    source = _upload(client, study["id"], "a.md", "# 旧\n旧内容").json()
    assert len(client.get(f"/api/sources/{source['id']}").json()["chunks"]) == 1

    # 改磁盘文件模拟"内容更新后重解析"
    with Session(get_engine()) as db:
        raw_path = Path(db.get(Source, source["id"]).raw_path)
    raw_path.write_text("# 新\n新内容", encoding="utf-8")

    resp = client.post(f"/api/sources/{source['id']}/reparse")
    assert resp.status_code == 200
    # 响应体在后台任务执行前已序列化(返回 pending);任务由 TestClient 同步跑完
    detail = client.get(f"/api/sources/{source['id']}").json()
    assert detail["parse_status"] == "ready"
    detail = client.get(f"/api/sources/{source['id']}").json()
    assert detail["chunks"][0]["content"].startswith("# 新")
