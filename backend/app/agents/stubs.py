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
    if "__TASK__FEYNMAN__" in text:
        return _feynman(text)
    if "__TASK__LECTURE__" in text:
        return _lecture(text)
    if "__TASK__QUIZ_GEN__" in text:
        return _quiz_gen(text)
    if "__TASK__QUIZ_GRADE__" in text:
        return _quiz_grade(text)
    if "__TASK__DEPS_INFER__" in text:
        return _deps_infer(text)
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


def _feynman(text: str) -> str:
    chunks = _load_chunks(text)
    first = chunks[0] if chunks else {"chunk_id": 0, "heading_path": ""}
    m = re.search(r"学习者对知识点的解释:(.*)", text, re.DOTALL)
    answer = (m.group(1).strip() if m else "")[:200]
    correct = len(answer) >= 15  # 确定性:有实质内容视为基本正确
    verdict = "解释正确" if correct else "解释里有几处偏差"
    return (
        f"{verdict}。{('你抓住了核心。' if correct else '建议对照资料再核对表述。')}"
        f"追问:你能说说「{first.get('heading_path') or '这个知识点'}」在实际代码里会怎么体现吗?[1]"
    )


def _quiz_gen(text: str) -> str:
    chunks = _load_chunks(text)
    first = chunks[0] if chunks else {"chunk_id": 0, "content": "", "heading_path": ""}
    body = _HEADING.sub("", str(first.get("content", ""))).strip()
    sentence = body.split("。")[0].strip() or body[:30]
    words = [w for w in re.split(r"[,,。; ;]", sentence) if len(w) >= 2]
    answer = words[0] if words else "概念"
    blanked = sentence.replace(answer, "____", 1)
    return json.dumps(
        {
            "quizzes": [
                {
                    "q_type": "objective",
                    "question": f"填空:{blanked}",
                    "options": [answer, "以上都不对", "无法从资料判断", "资料未提及"],
                    "answer": answer,
                    "chunk_id": first.get("chunk_id"),
                },
                {
                    "q_type": "objective",
                    "question": f"以下哪项正确描述了「{first.get('heading_path') or '本节'}」?",
                    "options": [sentence, "与资料相反的说法", "无关领域的说法", "资料未涉及"],
                    "answer": sentence,
                    "chunk_id": first.get("chunk_id"),
                },
                {
                    "q_type": "short_answer",
                    "question": f"用自己的话解释:{first.get('heading_path') or body[:20]}",
                    "options": [],
                    "answer": sentence,
                    "chunk_id": first.get("chunk_id"),
                },
            ]
        },
        ensure_ascii=False,
    )


def _quiz_grade(text: str) -> str:
    m = re.search(r"```quiz\n(.*?)\n```", text, re.DOTALL)
    try:
        data = json.loads(m.group(1)) if m else {}
    except json.JSONDecodeError:
        data = {}
    reference = data.get("reference", "")
    answer = data.get("answer", "")
    # 确定性判分:字符二元组重叠率 >0.3 视为掌握核心概念
    ref_bigrams = {reference[i : i + 2] for i in range(len(reference) - 1)}
    ans_bigrams = {answer[i : i + 2] for i in range(len(answer) - 1)}
    overlap = len(ref_bigrams & ans_bigrams) / max(len(ref_bigrams), 1)
    correct = overlap > 0.3
    feedback = (
        f"核心概念一致(重叠率 {overlap:.0%}),通过。"
        if correct
        else f"与参考答案重叠不足({overlap:.0%}),建议回看源文后复述要点。"
    )
    return json.dumps({"is_correct": correct, "feedback": feedback}, ensure_ascii=False)


def _deps_infer(text: str) -> str:
    m = re.search(r"```kps\n(.*?)\n```", text, re.DOTALL)
    try:
        kps = json.loads(m.group(1)) if m else []
    except json.JSONDecodeError:
        kps = []
    # 确定性推断:列表顺序即章节顺序,相邻链式依赖
    edges = [
        {"kp": kps[i]["name"], "depends_on": kps[i - 1]["name"]}
        for i in range(1, len(kps))
    ]
    return json.dumps({"edges": edges}, ensure_ascii=False)
