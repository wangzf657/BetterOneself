"""M2-02/03:依赖图落库、知识点编辑(改名/删除/新增/合并)。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Card, KnowledgePoint
from tests.util import setup_study_with_kp


def test_deps_stored_after_decompose(client):
    ctx = setup_study_with_kp(client)
    with Session(get_engine()) as db:
        edges = db.execute(select(
            __import__("app.models", fromlist=["KpDependency"]).KpDependency
        )).scalars().fetchall()
        assert edges, "上传后应推断出依赖边"
        # 无自环
        assert all(e.kp_id != e.depends_on_kp_id for e in edges)

    graph = client.get(f"/api/studies/{ctx['study']['id']}/kp-graph").json()
    assert len(graph["nodes"]) >= 3
    assert len(graph["edges"]) >= 1
    node_ids = {n["id"] for n in graph["nodes"]}
    assert all(e["source"] in node_ids and e["depends_on"] in node_ids for e in graph["edges"])


def test_rename_and_summary(client):
    ctx = setup_study_with_kp(client)
    resp = client.patch(
        f"/api/kps/{ctx['kp']['id']}",
        json={"name": "移动语义(进阶)", "summary": "赋值与所有权转移"},
    )
    assert resp.status_code == 200
    tree = client.get(f"/api/studies/{ctx['study']['id']}/knowledge").json()

    def find(nodes):
        for n in nodes:
            if n["id"] == ctx["kp"]["id"]:
                return n
            hit = find(n["children"])
            if hit:
                return hit

    assert find(tree)["name"] == "移动语义(进阶)"


def test_delete_kp_cascades_cards_and_tasks(client):
    ctx = setup_study_with_kp(client)
    kp = ctx["kp"]
    card = client.post(
        f"/api/studies/{ctx['study']['id']}/cards",
        json={"kp_id": kp["id"], "front": "q", "back_md": "a"},
    ).json()

    resp = client.delete(f"/api/kps/{kp['id']}")
    assert resp.status_code == 204
    with Session(get_engine()) as db:
        assert db.get(Card, card["id"]) is None  # 关联卡片随删
        assert db.get(KnowledgePoint, kp["id"]) is None
    # 子节点(若被删的是父)提为根——这里删的是叶子,树仍完整
    tree = client.get(f"/api/studies/{ctx['study']['id']}/knowledge").json()

    def count(nodes):
        return sum(1 + count(n["children"]) for n in nodes)

    assert count(tree) >= 2


def test_create_and_merge_kp(client):
    ctx = setup_study_with_kp(client)
    kp = ctx["kp"]

    # 补充一个兄弟节点
    created = client.post(
        f"/api/studies/{ctx['study']['id']}/kps",
        json={"name": "移动语义补充", "summary": "Copy 语义对比", "parent_id": None},
    ).json()
    assert created["id"]

    # 卡片挂在 source 上,合并后转移到 target
    card = client.post(
        f"/api/studies/{ctx['study']['id']}/cards",
        json={"kp_id": created["id"], "front": "合并卡", "back_md": "b"},
    ).json()

    merged = client.post(
        f"/api/kps/{created['id']}/merge", json={"target_id": kp["id"]}
    ).json()
    assert merged["id"] == kp["id"]
    with Session(get_engine()) as db:
        assert db.get(Card, card["id"]).kp_id == kp["id"]
        assert db.get(KnowledgePoint, created["id"]) is None

    # 不能合并到自己的后代
    child = client.post(
        f"/api/studies/{ctx['study']['id']}/kps",
        json={"name": "临时", "parent_id": kp["id"]},
    ).json()
    resp = client.post(f"/api/kps/{kp['id']}/merge", json={"target_id": child["id"]})
    assert resp.status_code == 422
