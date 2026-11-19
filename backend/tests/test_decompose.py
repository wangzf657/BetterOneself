"""M2-01/06:拆解流水线。装配逻辑单测 + 上传→自动拆解集成 + 拆解状态可见与重试。"""

import io
from types import SimpleNamespace

from app.agents.decompose import assemble_node
from app.models import UsageDay


def _state(extracted, chunks):
    return {"extracted": extracted, "chunks": chunks}


def _flatten(nodes):
    for n in nodes:
        yield n
        yield from _flatten(n["children"])


def test_assemble_merges_same_name_and_drops_invalid_refs():
    state = _state(
        [
            {"name": "移动语义", "summary": "a", "refs": [1, 99]},
            {"name": "移动 语义", "summary": "", "refs": [2]},
            {"name": "推断点", "summary": "", "refs": []},
        ],
        [
            {"chunk_id": 1, "heading_path": "Rust > 移动语义"},
            {"chunk_id": 2, "heading_path": "Rust > 借用"},
        ],
    )
    tree = assemble_node(state)["tree"]
    by_name = {n["name"]: n for n in _flatten(tree)}
    assert by_name["移动语义"]["refs"] == [1, 2]  # 去重合并,无效 ref 99 被裁
    assert by_name["推断点"]["ai_inferred"] is True
    assert by_name["移动语义"]["ai_inferred"] is False


def test_assemble_groups_children_under_top_heading():
    state = _state(
        [
            {"name": "移动语义", "summary": "", "refs": [1]},
            {"name": "借用", "summary": "", "refs": [2]},
            {"name": "独立点", "summary": "", "refs": [3]},
        ],
        [
            {"chunk_id": 1, "heading_path": "Rust 基础 > 移动语义"},
            {"chunk_id": 2, "heading_path": "Rust 基础 > 借用"},
            {"chunk_id": 3, "heading_path": "其他章"},
        ],
    )
    tree = assemble_node(state)["tree"]
    all_nodes = {n["name"]: n for n in _flatten(tree)}
    assert {c["name"] for c in all_nodes["Rust 基础"]["children"]} == {"移动语义", "借用"}
    # 结构父节点挂首个匹配切片,因此非 AI 推断
    assert all_nodes["Rust 基础"]["ai_inferred"] is False
    assert all_nodes["独立点"]["children"] == []
    # 独立点父节点"其他章"锚定到 chunk 3,非 AI 推断
    assert all_nodes["其他章"]["ai_inferred"] is False
    assert all_nodes["其他章"]["refs"] == [3]


def test_assemble_reuses_kp_as_parent_when_name_matches():
    state = _state(
        [
            {"name": "Rust 基础", "summary": "章概览", "refs": [1]},
            {"name": "移动语义", "summary": "", "refs": [2]},
        ],
        [
            {"chunk_id": 1, "heading_path": "Rust 基础"},
            {"chunk_id": 2, "heading_path": "Rust 基础 > 移动语义"},
        ],
    )
    tree = assemble_node(state)["tree"]
    assert len(tree) == 1
    assert tree[0]["name"] == "Rust 基础"
    assert [c["name"] for c in tree[0]["children"]] == ["移动语义"]


MD_DOC = "# Rust 基础\n概览。\n\n## 移动语义\n赋值即移动。\n\n## 借用\n引用不拥有值。"


def test_upload_md_auto_decomposes_to_kp_tree(client):
    study = client.post("/api/studies", json={"name": "Rust", "goal": "学会"}).json()
    client.post(
        f"/api/studies/{study['id']}/sources",
        files={
            "file": ("rust.md", io.BytesIO(MD_DOC.encode()), "text/markdown"),
        },
    )

    tree = client.get(f"/api/studies/{study['id']}/knowledge").json()
    tops = {n["name"]: n for n in tree}
    assert {"Rust 基础"} <= set(tops)
    children = {c["name"] for c in tops["Rust 基础"]["children"]}
    assert {"移动语义", "借用"} <= children
    # 每个 Kp 的 refs 指向真实 chunk,可跳转源文
    move = next(c for c in tops["Rust 基础"]["children"] if c["name"] == "移动语义")
    assert move["refs"] and move["refs"][0]["heading_path"] == "Rust 基础 > 移动语义"
    assert move["ai_inferred"] is False


def test_reparse_regenerates_tree_without_duplicates(client):
    study = client.post("/api/studies", json={"name": "Rust", "goal": "g"}).json()
    src = client.post(
        f"/api/studies/{study['id']}/sources",
        files={"file": ("a.md", io.BytesIO(b"# A\nx\n\n## B\ny"), "text/markdown")},
    ).json()
    client.post(f"/api/sources/{src['id']}/reparse")

    tree = client.get(f"/api/studies/{study['id']}/knowledge").json()
    names = [n["name"] for n in tree] + [c["name"] for n in tree for c in n["children"]]
    assert len(names) == len(set(names)), "重解析后知识点不应重复"


def test_record_usage_with_real_response(db):
    """回归(M2-01):真实 LLM 调用成功后记用量不得抛错——曾因局部变量遮蔽 usage 模块,
    每批拆解在记用量时 AttributeError 全部失败且被静默吞掉。"""
    from sqlalchemy import select

    from app.agents import llm

    resp = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))
    llm._record_usage("decompose", resp)
    row = db.scalar(select(UsageDay).where(UsageDay.scene == "decompose"))
    assert row is not None and row.prompt_tokens == 10 and row.requests == 1


def test_decompose_status_done_after_import(client):
    study = client.post("/api/studies", json={"name": "Rust", "goal": "g"}).json()
    assert client.get(f"/api/studies/{study['id']}/decompose-status").json() == {
        "status": "idle",
        "error": None,
    }
    client.post(
        f"/api/studies/{study['id']}/sources",
        files={"file": ("a.md", io.BytesIO("# A\n内容".encode()), "text/markdown")},
    )
    assert client.get(f"/api/studies/{study['id']}/decompose-status").json()["status"] == "done"


def test_decompose_failure_marks_study_and_retry_works(client, monkeypatch):
    """拆解批次全败不得静默成功:状态落 failed 可见,重试端点能恢复到 done。"""
    from app.agents import decompose as decompose_mod

    study = client.post("/api/studies", json={"name": "Rust", "goal": "g"}).json()
    monkeypatch.setattr(
        decompose_mod,
        "run_pipeline",
        lambda chunks: {"tree": [], "errors": ["batch@0: 模型不可用"]},
    )
    client.post(
        f"/api/studies/{study['id']}/sources",
        files={"file": ("a.md", io.BytesIO("# A\n内容".encode()), "text/markdown")},
    )
    status = client.get(f"/api/studies/{study['id']}/decompose-status").json()
    assert status["status"] == "failed"
    assert "模型不可用" in status["error"]

    monkeypatch.undo()  # 恢复真实(stub)流水线后重试
    resp = client.post(f"/api/studies/{study['id']}/decompose")
    assert resp.status_code == 202
    assert client.get(f"/api/studies/{study['id']}/decompose-status").json()["status"] == "done"
    tree = client.get(f"/api/studies/{study['id']}/knowledge").json()
    assert tree, "重试后应拆出知识点"


def test_stub_extracts_kp_from_fenced_chunk():
    """stub 对含代码围栏的切片仍能解析出知识点(raw_decode 不被内部 ``` 截断)。"""
    from app.agents import prompts, stubs

    chunk = {
        "chunk_id": 7,
        "heading_path": "工具 > 声明工具",
        "content": "```\ntool_calls: [{name: 'x'}]\n```",
    }
    out = stubs.stub_chat(prompts.decompose_messages([chunk]))
    assert '"kps"' in out and "声明工具" in out
