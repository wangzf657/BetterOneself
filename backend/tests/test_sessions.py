"""M3-02/03:会话创建、SSE 流式讲解(带引用)、苏格拉底开关。"""

import io
import json


def _setup_study_with_md(client) -> tuple[int, int]:
    study = client.post("/api/studies", json={"name": "Rust", "goal": "学会"}).json()
    client.post(
        f"/api/studies/{study['id']}/sources",
        files={
            "file": (
                "rust.md",
                io.BytesIO("# Rust 基础\n概览。\n\n## 移动语义\n赋值即移动。".encode()),
                "text/markdown",
            )
        },
    )
    tree = client.get(f"/api/studies/{study['id']}/knowledge").json()
    kp_id = _find_kp(tree, "移动语义")
    return study["id"], kp_id


def _find_kp(nodes, name):
    for n in nodes:
        if n["name"] == name:
            return n["id"]
        found = _find_kp(n["children"], name)
        if found:
            return found
    return None


def _collect_sse(client, url, payload):
    events = []
    with client.stream("POST", url, json=payload) as resp:
        assert resp.status_code == 200
        event = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: ") and event:
                events.append((event, json.loads(line[6:])))
    return events


def test_chat_streams_answer_with_citations(client):
    study_id, kp_id = _setup_study_with_md(client)
    session = client.post(
        f"/api/studies/{study_id}/sessions", json={"kp_id": kp_id}
    ).json()
    assert session["socratic_mode"] is True  # 默认引导式(M3-03)

    events = _collect_sse(
        client, f"/api/sessions/{session['id']}/chat", {"content": "什么是移动语义?"}
    )
    kinds = [e for e, _ in events]
    assert "delta" in kinds and kinds[-1] == "done"

    done = events[-1][1]
    assert done["content"], "应有完整回答"
    # 引用必须指向真实存在的 chunk(stub 讲解固定引用 [1])
    assert done["citations"], "回答必须带来源引用(M3-02)"
    first = done["citations"][0]
    chunk_detail = client.get(f"/api/sources/{first['source_id']}").json()
    assert any(c["id"] == first["chunk_id"] for c in chunk_detail["chunks"])


def test_messages_persisted_and_history_carried(client):
    study_id, kp_id = _setup_study_with_md(client)
    session = client.post(
        f"/api/studies/{study_id}/sessions", json={"kp_id": kp_id}
    ).json()
    _collect_sse(client, f"/api/sessions/{session['id']}/chat", {"content": "第一问"})
    _collect_sse(client, f"/api/sessions/{session['id']}/chat", {"content": "第二问"})

    detail = client.get(f"/api/sessions/{session['id']}").json()
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]
    assistant = detail["messages"][1]
    assert assistant["citations"], "历史消息的引用应已解析存储"


def test_socratic_toggle(client):
    study_id, _ = _setup_study_with_md(client)
    session = client.post(f"/api/studies/{study_id}/sessions", json={}).json()

    patched = client.patch(
        f"/api/sessions/{session['id']}/socratic", json={"socratic_mode": False}
    )
    assert patched.json()["socratic_mode"] is False

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert detail["socratic_mode"] is False


def test_chat_on_missing_session_404(client):
    resp = client.post("/api/sessions/999/chat", json={"content": "hi"})
    assert resp.status_code == 404
