"""测试公共工具。"""

import io

MD_DOC = "# Rust 基础\n概览。\n\n## 移动语义\n赋值即移动,原变量不可用。\n\n## 借用\n引用不拥有值。"


def setup_study_with_kp(client) -> dict:
    """建项目→导 MD→拆解→返回 study/移动语义 kp。"""
    study = client.post("/api/studies", json={"name": "Rust", "goal": "学会"}).json()
    client.post(
        f"/api/studies/{study['id']}/sources",
        files={"file": ("rust.md", io.BytesIO(MD_DOC.encode()), "text/markdown")},
    )
    tree = client.get(f"/api/studies/{study['id']}/knowledge").json()
    kp = find_kp(tree, "移动语义")
    assert kp is not None
    return {"study": study, "kp": kp}


def find_kp(nodes, name):
    for n in nodes:
        if n["name"] == name:
            return n
        hit = find_kp(n["children"], name)
        if hit:
            return hit
    return None
