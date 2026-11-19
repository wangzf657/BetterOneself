"""拆解流水线(LangGraph,技术总纲 2.3):切片分批抽取 → 树装配去重(M2-01) → 依赖推断(M2-02)。

装配规则:
- 同名知识点(规范化后)合并,refs 取并集
- refs 指向不存在 chunk 的条目被裁掉;裁空后标 ai_inferred
- 父节点 = 主参考切片顶级标题;父与已有知识点同名则复用,否则建结构父节点并挂首个匹配切片

依赖以 name 对输出(树内 name 全局唯一),service 落库时映射 id 并做环检测。
"""

from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.agents import llm, prompts

BATCH_SIZE = 8


class ExtractedKp(BaseModel):
    name: str
    summary: str = ""
    kp_type: Literal["concept", "fact", "procedure"] = "concept"
    refs: list[int] = Field(default_factory=list)


class ExtractOut(BaseModel):
    kps: list[ExtractedKp]


class DepEdge(BaseModel):
    kp: str
    depends_on: str


class DepsOut(BaseModel):
    edges: list[DepEdge]


class DecomposeState(TypedDict, total=False):
    chunks: list[dict]
    extracted: list[dict]
    tree: list[dict]
    dependencies: list[dict]
    errors: list[str]


def extract_node(state: DecomposeState) -> dict[str, Any]:
    extracted: list[dict] = []
    errors: list[str] = []
    chunks = state["chunks"]
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        try:
            parsed = llm.parse_json(
                prompts.decompose_messages(batch), ExtractOut, scene="decompose"
            )
            extracted.extend(kp.model_dump() for kp in parsed.kps)
        except Exception as err:  # noqa: BLE001 单批失败不拖垮整体
            errors.append(f"batch@{i}: {err}")
    return {"extracted": extracted, "errors": errors}


def _norm(name: str) -> str:
    return "".join(name.split()).lower()


def assemble_node(state: DecomposeState) -> dict[str, Any]:
    chunks = state["chunks"]
    heading_of = {c["chunk_id"]: c.get("heading_path", "") for c in chunks}

    # 1) 同名去重,refs 只留真实存在的 chunk
    by_name: dict[str, dict] = {}
    order: list[dict] = []
    for kp in state["extracted"]:
        name = kp.get("name", "").strip()
        if not name:
            continue
        key = _norm(name)
        refs = [r for r in kp.get("refs", []) if r in heading_of]
        if key in by_name:
            existing = by_name[key]
            existing["refs"] = list(dict.fromkeys(existing["refs"] + refs))
            existing["summary"] = existing["summary"] or kp.get("summary", "")
            existing["ai_inferred"] = not existing["refs"]
        else:
            item = {
                "name": name,
                "summary": kp.get("summary", ""),
                "kp_type": kp.get("kp_type", "concept"),
                "refs": list(dict.fromkeys(refs)),
                "children": [],
            }
            item["ai_inferred"] = not item["refs"]
            by_name[key] = item
            order.append(item)

    # 2) 计算父节点名(主参考切片的顶级标题,不与自身同名)
    for item in order:
        parent = None
        if item["refs"]:
            path = heading_of.get(item["refs"][0], "")
            segs = [s.strip() for s in path.split(" > ") if s.strip()]
            if segs and _norm(segs[0]) != _norm(item["name"]):
                parent = segs[0]
        item["_parent"] = parent

    # 3) 建结构父节点:与已有知识点同名则复用,否则新建并挂首个匹配切片
    parents: dict[str, dict] = {}
    for item in list(order):  # 快照:循环中会向 order 追加结构父节点
        pname = item["_parent"]
        if pname is None:
            continue
        pkey = _norm(pname)
        if pkey not in parents:
            if pkey in by_name:
                parents[pkey] = by_name[pkey]
            else:
                first_chunk = next(
                    (
                        c["chunk_id"]
                        for c in chunks
                        if c.get("heading_path", "").split(" > ")[0].strip() == pname
                    ),
                    None,
                )
                node = {
                    "name": pname,
                    "summary": "",
                    "kp_type": "concept",
                    "refs": [first_chunk] if first_chunk is not None else [],
                    "children": [],
                    "_parent": None,
                }
                node["ai_inferred"] = not node["refs"]
                by_name[pkey] = node
                order.append(node)
                parents[pkey] = node

    # 4) 挂树
    roots: list[dict] = []
    for item in order:
        item.setdefault("children", [])
        pkey = item.pop("_parent", None)
        if pkey is not None and _norm(pkey) in parents:
            parents[_norm(pkey)]["children"].append(item)
        else:
            roots.append(item)
    return {"tree": roots}


def deps_node(state: DecomposeState) -> dict[str, Any]:
    """依赖推断(M2-02):对装配后的知识点推断前后依赖,输出 name 对。"""
    flat: list[dict] = []

    def walk(nodes):
        for n in nodes:
            flat.append({"name": n["name"], "summary": n.get("summary", "")})
            walk(n.get("children", []))

    walk(state["tree"])
    if len(flat) < 2:
        return {"dependencies": []}
    try:
        out = llm.parse_json(prompts.deps_messages(flat), DepsOut, scene="decompose")
        names = {item["name"] for item in flat}
        edges = [
            {"kp": e.kp, "depends_on": e.depends_on}
            for e in out.edges
            if e.kp in names and e.depends_on in names and e.kp != e.depends_on
        ]
        return {"dependencies": edges}
    except Exception:  # noqa: BLE001 依赖推断失败不阻塞拆解主流程
        return {"dependencies": []}


def build_graph():
    graph = StateGraph(DecomposeState)
    graph.add_node("extract", extract_node)
    graph.add_node("assemble", assemble_node)
    graph.add_node("deps", deps_node)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "assemble")
    graph.add_edge("assemble", "deps")
    graph.add_edge("deps", END)
    return graph.compile()


_graph = None


def run_pipeline(chunks: list[dict]) -> dict:
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph.invoke({"chunks": chunks})
