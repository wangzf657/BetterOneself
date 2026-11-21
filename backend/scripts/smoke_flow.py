"""开发冒烟脚本：桩 LLM 下走通「导入 → 树 → 学 → 测 → 点亮 → 排除/恢复」。

用法：uv run python scripts/smoke_flow.py [base_url]（默认 http://127.0.0.1:8765）
"""

from __future__ import annotations

import io
import json
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"

BOOK = """第一章 Agent 导论

Agent 是能够感知环境、做出决策并执行动作的系统。本章介绍 Agent 的基本组成与运行循环。

1.1 什么是 Agent

Agent 的核心是决策循环：观察、思考、行动。与普通程序不同，Agent 的行为由目标驱动而非固定流程。信息筛选的目标是保留与当前任务直接相关的证据，而不是收集得越多越好。

1.2 Agent 的组成

一个 Agent 通常由感知模块、记忆模块、规划模块与执行模块组成。记忆模块决定它能利用多少历史信息；规划模块把目标拆成可执行的步骤。

第二章 上下文工程

上下文窗口并不是越长越好。信息筛选的目标，是保留与当前任务直接相关的证据。压缩不是简单缩短文字，而是降低无关信息对注意力的干扰。

2.1 信息筛选

筛选标准有三条：任务相关性、时效性与可信度。资料放得更全反而可能让回答更差，因为信噪比下降了。

2.2 信息压缩

压缩的本质是取舍：优先保留结论与关键证据，过程性细节可以按需取用。

第三章 附录 习题答案

这里放的是各章习题的参考答案，不是学习内容。
"""


def walk(nodes: list[dict]) -> list[dict]:
    out: list[dict] = []
    for n in nodes:
        out.append(n)
        out.extend(walk(n.get("children", [])))
    return out


def main() -> None:
    files = {"file": ("agent-book.txt", io.BytesIO(BOOK.encode("utf-8")), "text/plain")}
    r = httpx.post(
        f"{BASE}/api/studies",
        data={"name": "Agent 入门"},
        files=files,
        headers={"Idempotency-Key": "smoke-flow"},
        timeout=30,
    )
    print("create:", r.status_code, r.json().get("id"))
    sid = r.json()["id"]

    p: dict = {}
    for _ in range(30):
        p = httpx.get(f"{BASE}/api/studies/{sid}/progress", timeout=10).json()
        if p["parse"]["status"] in ("parsed", "failed") and p["outline"]["status"] in (
            "ready",
            "skipped",
            "failed",
        ):
            break
        time.sleep(1)
    print("progress:", json.dumps(p, ensure_ascii=False))

    tree = httpx.get(f"{BASE}/api/studies/{sid}/knowledge", timeout=10).json()
    print("tree progress:", tree["progress"])
    units = [n for n in walk(tree["nodes"]) if n["is_learning_unit"]]
    print("units:", [(u["id"], u["name"], u["status"]) for u in units])
    target = units[0]

    s = httpx.post(f"{BASE}/api/studies/{sid}/sessions", json={"kp_id": target["id"]}, timeout=10)
    sess = s.json()["session"]
    print("session:", sess["id"])

    with httpx.stream("POST", f"{BASE}/api/sessions/{sess['id']}/opening", timeout=60) as resp:
        print("opening SSE status:", resp.status_code)
        got = [line for line in resp.iter_lines() if line.startswith("data:")]
        print("opening SSE data events:", len(got))

    det = httpx.get(f"{BASE}/api/sessions/{sess['id']}", timeout=10).json()
    first = det["messages"][0]
    print("first msg refs:", [r["chunk_id"] for r in first["refs"]], "| head:", first["content"][:36])

    q = httpx.post(f"{BASE}/api/sessions/{sess['id']}/quizzes", timeout=30).json()
    print("quiz:", q["quiz_id"], "graded:", q["graded_count"], "pass_line:", q["pass_line"])
    print("stems:", [x["stem"][:16] for x in q["questions"]])
    assert "answer" not in json.dumps(q["questions"]), "PUBLIC FACE LEAK"

    answers = [
        {"no": 1, "choice": "B"},
        {"no": 2, "choice": "C"},
        {"no": 3, "choice": False},
        {"no": 4, "choice": False},
        {"no": 5, "text": "因为无关信息多了会分散注意力。"},
    ]
    a = httpx.post(f"{BASE}/api/quizzes/{q['quiz_id']}/answer", json={"answers": answers}, timeout=60).json()
    print("answered: correct=", a["correct_count"], "passed=", a["passed"], "lighted=", a["lighted"])

    tree2 = httpx.get(f"{BASE}/api/studies/{sid}/knowledge", timeout=10).json()
    units2 = {u["id"]: u for u in walk(tree2["nodes"]) if u["is_learning_unit"]}
    print("target status now:", units2[target["id"]]["status"], "| progress:", tree2["progress"])

    q2 = httpx.post(f"{BASE}/api/sessions/{sess['id']}/quizzes", timeout=30).json()
    print("re-quiz new stems:", [x["stem"][:16] for x in q2["questions"]])
    wrong = [
        {"no": 1, "choice": "A"},
        {"no": 2, "choice": "A"},
        {"no": 3, "choice": True},
        {"no": 4, "choice": True},
        {"no": 5, "text": "不知道"},
    ]
    a2 = httpx.post(f"{BASE}/api/quizzes/{q2['quiz_id']}/answer", json={"answers": wrong}, timeout=60).json()
    print("re-quiz passed(False?):", a2["passed"], "| already_lighted(True?):", a2["lighted"]["already_lighted"])
    units3 = {
        u["id"]: u
        for u in walk(httpx.get(f"{BASE}/api/studies/{sid}/knowledge", timeout=10).json()["nodes"])
        if u["is_learning_unit"]
    }
    print("still lighted:", units3[target["id"]]["status"])

    hist = httpx.get(f"{BASE}/api/kps/{target['id']}/quizzes", timeout=10).json()
    print("history quizzes:", len(hist), "per_q of latest:", [(x["no"], x.get("correct")) for x in hist[0]["per_question"]])

    note = httpx.put(
        f"{BASE}/api/kps/{target['id']}/note",
        json={"content_md": "# 我的想法\n过滤不是越多越好"},
        timeout=10,
    )
    print("note put:", note.status_code, "| get:", httpx.get(f"{BASE}/api/kps/{target['id']}/note", timeout=10).json()["content_md"][:12])

    imp = httpx.get(f"{BASE}/api/kps/{target['id']}/exclude-impact", timeout=10).json()
    print("exclude-impact:", imp["progress_before"], "->", imp["progress_after"], "lighted_affected:", imp["lighted_affected"])
    ex = httpx.post(f"{BASE}/api/kps/{target['id']}/exclude", json={"reason": "测试"}, timeout=10).json()
    print("exclude:", ex["progress_before"], "->", ex["progress_after"])
    rs = httpx.post(f"{BASE}/api/kps/{target['id']}/restore", timeout=10).json()
    print("restore:", rs["progress_before"], "->", rs["progress_after"])

    ev = httpx.get(f"{BASE}/api/studies/{sid}/outline/events?limit=12", timeout=10).json()
    print("events:", [(e["event_type"], e["actor"]) for e in ev][:10])
    st = httpx.get(f"{BASE}/api/settings", timeout=10).json()
    print("settings llm masked:", st["llm"]["api_key"], "| embed status:", st["embed"]["status"])
    print("usage:", httpx.get(f"{BASE}/api/usage", timeout=10).json())
    print("SMOKE OK")


if __name__ == "__main__":
    main()
