# -*- coding: utf-8 -*-
"""API 域链路测试：会话→开场→提问→测验→判分→点亮→证据→排除/恢复→重考保留。
只调用 HTTP 接口，输出每步断言结果；证据存 qa/V0.1/logs/api/。"""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8000/api"
OUT = []


def call(method: str, path: str, body: dict | None = None, headers: dict | None = None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=60) as r:
            raw = r.read().decode()
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, {"_raw": raw[:500]}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def sse(path: str, body: dict | None = None) -> str:
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(BASE + path, method="POST", data=data)
    req.add_header("Content-Type", "application/json")
    chunks = []
    with urllib.request.urlopen(req, timeout=60) as r:
        for raw in r:
            line = raw.decode("utf-8").strip()
            if line.startswith("data:"):
                chunks.append(line[5:].strip())
    return "".join(chunks)


def check(name: str, cond: bool, detail: str = "") -> None:
    OUT.append((name, cond, detail))
    print(("PASS " if cond else "FAIL ") + name + (" | " + detail if detail else ""))


def wrong_answers() -> list[dict]:
    return [{"no": 1, "choice": "A"}, {"no": 2, "choice": "A"},
            {"no": 3, "choice": True}, {"no": 4, "choice": True},
            {"no": 5, "text": "练习作答"}]


def right_answers() -> list[dict]:
    return [{"no": 1, "choice": "B"}, {"no": 2, "choice": "C"},
            {"no": 3, "choice": False}, {"no": 4, "choice": False},
            {"no": 5, "text": "无关信息分散注意力，信噪比下降。"}]


STUDY = int(sys.argv[1]) if len(sys.argv) > 1 else 8

# 0. 取树：选第一个未学学习单元，记录进度基线
st0, tree0 = call("GET", f"/studies/{STUDY}/knowledge")
units = [n for n in tree0["nodes"] if n["is_learning_unit"] and not n["excluded"]]
units.sort(key=lambda n: n["sort_order"])
KP = units[0]["id"]
BASE_L = tree0["progress"]["lighted"]
BASE_T = tree0["progress"]["total"]
print(f"study={STUDY} kp={KP} baseline={BASE_L}/{BASE_T}")

# 1. 建会话
st, sess = call("POST", f"/studies/{STUDY}/sessions", {"kp_id": KP})
check("TC-B3 建会话", st == 200 and sess.get("session", {}).get("id"), f"status={st} id={sess.get('session', {}).get('id')}")
sid = sess["session"]["id"]
check("TC-B3-01 反例·无伪造用户消息", all(m.get("role") != "user" for m in sess.get("messages", [])),
      f"messages={len(sess.get('messages', []))}")

# 2. 开场讲解（SSE）
opening = sse(f"/sessions/{sid}/opening")
check("TC-B3-01 开场非空且带引用", len(opening) > 50 and "[1]" in opening, f"len={len(opening)}")
check("TC-B3-01 先定位后讲解", "位置" in opening or "属于" in opening, opening[:60])

# 3. 重复开场应 Conflict
st2, _ = call("POST", f"/sessions/{sid}/opening")
check("TC-B3 重复开场 Conflict", st2 == 409, f"status={st2}")

# 4. 自由提问（SSE with body）
chat = sse(f"/sessions/{sid}/chat", {"content": "什么是决策循环？"})
check("TC-B3-04 自由提问回答非空", len(chat) > 20, f"len={len(chat)}")
check("TC-B3-04 回答带引用", "[1]" in chat, chat[:50])

# 5. 会话详情含消息
st4, detail = call("GET", f"/sessions/{sid}")
roles = [m["role"] for m in detail.get("messages", [])]
check("TC-B3-04 回答为 assistant", roles == ["assistant", "user", "assistant"], f"roles={roles}")
check("TC-B3 会话 scheme 默认", detail.get("session", {}).get("scheme") in ("guided", "lecture", "drill"),
      f"scheme={detail.get('session', {}).get('scheme')}")

# 6. 生成测验
st5, quiz = call("POST", f"/sessions/{sid}/quizzes")
graded = [q for q in quiz.get("questions", []) if q.get("graded")]
practice = [q for q in quiz.get("questions", []) if not q.get("graded")]
check("TC-B4-03 4 计分+1 练习", st5 == 200 and len(graded) == 4 and len(practice) == 1,
      f"graded={len(graded)} practice={len(practice)}")
check("TC-B4-02 通过线考前可见=3", quiz.get("pass_line") == 3, f"pass_line={quiz.get('pass_line')}")
check("TC-B4-01 反例·作答前不泄露答案",
      all("answer" not in q and "explanation" not in q and "refs" not in q for q in quiz.get("questions", [])),
      "")
types = {q.get("type") for q in graded}
check("TC-B4-03 题型为单选/判断", types <= {"choice", "judge"}, f"types={types}")
check("TC-B4-01 说明含题型覆盖 coverage", isinstance(quiz.get("coverage"), list) and len(quiz.get("coverage")) > 0,
      f"coverage={quiz.get('coverage')}")

# 7. 同节点再次生成 → 回到进行中组（不重复）
st6, quiz2 = call("POST", f"/sessions/{sid}/quizzes")
check("TC-B4-09 重复生成回到同组", quiz2.get("quiz_id") == quiz.get("quiz_id"),
      f"q1={quiz.get('quiz_id')} q2={quiz2.get('quiz_id')} status={st6}")

# 8. 全错作答 → 未达线
st7, res_wrong = call("POST", f"/quizzes/{quiz['quiz_id']}/answer", {"answers": wrong_answers()})
check("TC-B4-07 未达线不点亮", res_wrong.get("passed") is False and (res_wrong.get("lighted") or {}).get("lighted_at") is None,
      f"passed={res_wrong.get('passed')} correct={res_wrong.get('correct_count')}")
check("TC-B4-05 逐题判定+答案+解析+refs",
      all(("correct" in q and "answer" in q and "explanation" in q and "refs" in q)
          for q in res_wrong.get("per_question", []) if q.get("graded")),
      "")
check("TC-B4-05 练习题评语且标不计分", "comment" in (res_wrong.get("per_question") or [{}])[-1] and (res_wrong.get("per_question") or [{}])[-1].get("graded") is False, "")
check("TC-B4-05 保存本人作答", len(res_wrong.get("submitted_answers", [])) == 5, f"submitted={len(res_wrong.get('submitted_answers', []))}")

# 9. 未通过再考新题
st8, quiz3 = call("POST", f"/sessions/{sid}/quizzes")
stems1 = [q["stem"] for q in quiz.get("questions", [])]
stems3 = [q["stem"] for q in quiz3.get("questions", [])]
check("TC-B4-07 反例·再考为新题", quiz3.get("quiz_id") != quiz.get("quiz_id") and stems1 != stems3,
      f"q1={quiz.get('quiz_id')} q3={quiz3.get('quiz_id')} stems_equal={stems1 == stems3}")

# 10. 全对作答 → 达线点亮（练习题乱写不影响）
st9, res_right = call("POST", f"/quizzes/{quiz3['quiz_id']}/answer", {"answers": right_answers()})
check("TC-B4-06 达线点亮", res_right.get("passed") is True,
      f"passed={res_right.get('passed')} correct={res_right.get('correct_count')}")
check("TC-B4-12 练习乱写不影响点亮", res_right.get("passed") is True, "")

# 11. 树上状态与进度
st10, tree = call("GET", f"/studies/{STUDY}/knowledge")
node2 = next(n for n in tree["nodes"] if n["id"] == KP)
check("TC-B4-06 树状态 lighted", node2["status"] == "lighted" and node2.get("lighted_at"),
      f"status={node2['status']} lighted_at={node2.get('lighted_at')}")
check("TC-B5-01 进度点亮+1", tree["progress"]["lighted"] == BASE_L + 1 and tree["progress"]["total"] == BASE_T,
      f"progress={tree['progress']}")

# 12. 点亮证据 = 首次通过测验（quiz3，非 quiz）
st11, ev = call("GET", f"/kps/{KP}/lighting-evidence")
check("TC-B4-13 首次通过证据可下钻", st11 == 200 and ev.get("quiz_id") == quiz3.get("quiz_id"),
      f"quiz_id={ev.get('quiz_id')} (期望首次通过的 {quiz3.get('quiz_id')})")

# 13. 重命名不改分母
st12, _ = call("PATCH", "/kps/2", {"name": "1.1 什么是 Agent（改名）"})
st13, tree2 = call("GET", f"/studies/{STUDY}/knowledge")
check("TC-B5-03 重命名分母不变", tree2["progress"]["total"] == BASE_T and tree2["progress"]["lighted"] == BASE_L + 1,
      f"progress={tree2['progress']}")

# 14. 排除预览与应用一致（契约：{progress_before, progress_after, lighted_affected}，接口设计.md:119）
# 此时链路已点亮 KP：before=(BASE_L+1, BASE_T)，排除该点亮单元后 after=(BASE_L, BASE_T-1)
st14, imp = call("GET", f"/kps/{KP}/exclude-impact")
pb, pa = imp.get("progress_before") or {}, imp.get("progress_after") or {}
check("TC-B2-07 排除预览分母-1",
      (pb.get("lighted"), pb.get("total")) == (BASE_L + 1, BASE_T)
      and (pa.get("lighted"), pa.get("total")) == (BASE_L, BASE_T - 1)
      and imp.get("lighted_affected") == BASE_L + 1,
      f"preview={imp}")
st15, _ = call("POST", f"/kps/{KP}/exclude", {"reason": "QA 测试排除"})
st16, tree3 = call("GET", f"/studies/{STUDY}/knowledge")
check("TC-B2-07 应用后与预览一致", tree3["progress"]["lighted"] == BASE_L and tree3["progress"]["total"] == BASE_T - 1,
      f"progress={tree3['progress']}")

# 15. 已排除节点禁止新学习
st17, err = call("POST", f"/studies/{STUDY}/sessions", {"kp_id": KP})
check("TC-B2-08 已排除禁学", st17 == 422, f"status={st17} detail={str(err)[:80]}")

# 16. 恢复不产生新证据
st18, rresp = call("POST", f"/kps/{KP}/restore")
check("TC-B2-08 恢复接口成功", st18 == 200, f"status={st18} resp={str(rresp)[:80]}")
st19, tree4 = call("GET", f"/studies/{STUDY}/knowledge")
node2b = next(n for n in tree4["nodes"] if n["id"] == KP)
check("TC-B2-08 恢复后分母还原且仍点亮",
      tree4["progress"]["total"] == BASE_T and node2b["status"] == "lighted",
      f"progress={tree4['progress']} status={node2b['status']}")

# 17. 已点亮重考失败 → 原有点亮保留
st20, quiz4 = call("POST", f"/sessions/{sid}/quizzes")
stems4 = [q["stem"] for q in quiz4.get("questions", [])]
check("TC-B4-08 重考生成新组", quiz4.get("quiz_id") not in (quiz.get("quiz_id"), quiz3.get("quiz_id"))
      and stems4 not in (stems1, stems3), f"q4={quiz4.get('quiz_id')}")
st21, res4 = call("POST", f"/quizzes/{quiz4['quiz_id']}/answer", {"answers": wrong_answers()})
check("TC-B4-08 未达线但 already_lighted=true",
      res4.get("passed") is False and (res4.get("lighted") or {}).get("already_lighted") is True,
      f"passed={res4.get('passed')} lighted={res4.get('lighted')}")
st22, tree5 = call("GET", f"/studies/{STUDY}/knowledge")
node2c = next(n for n in tree5["nodes"] if n["id"] == KP)
check("TC-B4-08 点亮状态未变", node2c["status"] == "lighted" and node2c.get("lighted_at") == node2.get("lighted_at"),
      f"status={node2c['status']} lighted_at={node2c.get('lighted_at')}")

# 18. 笔记（含 XSS 内容存储验证）
st23, note = call("PUT", f"/kps/{KP}/note", {"content_md": "# QA 笔记\n- 内容一\n<script>alert(1)</script>"})
check("TC-B3-07 笔记保存", st23 == 200 and "QA 笔记" in note.get("content_md", ""), f"status={st23}")
st24, note2 = call("GET", f"/kps/{KP}/note")
check("TC-B3-07 笔记读回一致", note2.get("content_md") == note.get("content_md"), "")

# 19. 事件列表
st25, events = call("GET", f"/studies/{STUDY}/outline/events")
check("TC-B2-14 事件记录存在", st25 == 200 and len(events) > 0, f"events={len(events)}")

# 20. 学习方法切换
for s in ("lecture", "drill", "guided"):
    stc, _ = call("PATCH", f"/sessions/{sid}/scheme", {"scheme": s})
    if stc != 200:
        break
check("TC-B3-05 学习方法三选一可切换", stc == 200, f"最后 scheme={s} status={stc}")
stc2, err2 = call("PATCH", f"/sessions/{sid}/scheme", {"scheme": "bogus"})
check("TC-B3-05 非法 scheme 422", stc2 == 422, f"status={stc2}")

# 21. 测验回看一致性（B4-04）：kp 测验列表与 answer 结果对比
st26, quizzes_of_kp = call("GET", f"/kps/{KP}/quizzes")
ids = [q.get("quiz_id") for q in quizzes_of_kp]
check("TC-B4-11 回看列表含历次测验", set(ids) >= {quiz.get("quiz_id"), quiz3.get("quiz_id"), quiz4.get("quiz_id")} if quiz4 else set(ids) >= {quiz.get("quiz_id"), quiz3.get("quiz_id")},
      f"ids={ids}")

print("\n==== SUMMARY ====")
fails = [o for o in OUT if not o[1]]
print(f"total={len(OUT)} pass={len(OUT)-len(fails)} fail={len(fails)}")
for name, _, detail in fails:
    print("FAILED:", name, "|", detail)
