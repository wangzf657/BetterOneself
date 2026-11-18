"""确定性 LLM stub:按提示词里的 __TASK__ 标记生成结构可用的输出,测试与 E2E 零 token。

提示词约定:任务标记独占一行;需要模型阅读的数据放在 ```chunks JSON 块中。
"""

import json
import re

_CHUNKS = re.compile(r"```chunks\n(.*?)\n```", re.DOTALL)
_HEADING = re.compile(r"^#{1,2}\s+(.+)$", re.MULTILINE)


def stub_chat(messages: list[dict]) -> str:
    text = "\n".join(str(m.get("content", "")) for m in messages)
    if "__TASK__KNOWLEDGE_EXTRACT__" in text:
        return _knowledge_extract(text)
    if "__TASK__LECTURE__" in text:
        return _lecture(text)
    return "(stub)未识别任务,请检查提示词是否带 __TASK__ 标记。"


def _load_chunks(text: str) -> list[dict]:
    m = _CHUNKS.search(text)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
        return data if isinstance(data, list) else data.get("chunks", [])
    except json.JSONDecodeError:
        return []


def _knowledge_extract(text: str) -> str:
    kps: list[dict] = []
    seen: set[str] = set()
    for i, chunk in enumerate(_load_chunks(text)):
        content = chunk.get("content", "")
        m = _HEADING.search(content)
        name = m.group(1).strip() if m else (chunk.get("heading_path") or f"要点{i + 1}")
        if name in seen:
            continue
        seen.add(name)
        body = _HEADING.sub("", content).strip()
        kps.append({
            "name": name,
            "summary": body[:80],
            "kp_type": "concept",
            "refs": [chunk["chunk_id"]],
        })
    return json.dumps({"kps": kps}, ensure_ascii=False)


def _lecture(text: str) -> str:
    chunks = _load_chunks(text)
    if not chunks:
        return "资料中没有可用内容。"
    first = chunks[0]
    body = _HEADING.sub("", first.get("content", "")).strip()
    return f"{first.get('heading_path', '本节')} 的要点:{body[:120]}。以上内容来自资料 [1]。"
