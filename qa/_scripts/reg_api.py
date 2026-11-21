# -*- coding: utf-8 -*-
"""回归测试 API 脚本（修复后）：BUG-001 设置三语义 / BUG-002 桩用量 / BUG-003 幂等并发。
只调用 HTTP 接口与只读 DB 检查；证据存 qa/V0.1/logs/reg/。"""
import concurrent.futures
import glob
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000/api"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
TX = os.path.join(ROOT, "qa", "V0.1", "testdata", "QA书-TX-01.txt")
LOG = os.path.join(ROOT, "qa", "V0.1", "logs", "reg", "backend-8000.log")
OUT = []
RESULTS = {"bug001": [], "bug002": [], "bug003": []}


def call(method, path, body=None, headers=None, raw_body=None, content_type="application/json"):
    req = urllib.request.Request(BASE + path, method=method)
    if raw_body is not None:
        data = raw_body
        req.add_header("Content-Type", content_type)
    else:
        data = json.dumps(body).encode() if body is not None else None
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, data=data, timeout=120) as r:
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


def multipart(fields, file_field, file_path):
    boundary = "----QABoundary9231"
    body = []
    for k, v in fields.items():
        body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    fname = os.path.basename(file_path)
    body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{fname}\"\r\n"
                f"Content-Type: text/plain\r\n\r\n".encode())
    with open(file_path, "rb") as f:
        body.append(f.read())
    body.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(body), f"multipart/form-data; boundary={boundary}"


def check(group, name, cond, detail=""):
    OUT.append((group, name, cond, detail))
    RESULTS[group].append({"name": name, "pass": bool(cond), "detail": str(detail)[:300]})
    print(("PASS " if cond else "FAIL ") + f"[{group}] {name}" + (" | " + detail if detail else ""))


def db_readonly():
    cands = glob.glob(os.path.join(ROOT, "backend", "data_qa_reg", "*.db")) + \
        glob.glob(os.path.join(ROOT, "backend", "data_qa_reg", "**", "*.db"), recursive=True)
    assert cands, "no sqlite db found in data_qa_reg"
    conn = sqlite3.connect(f"file:{cands[0]}?mode=ro", uri=True)
    return conn


# ============ BUG-001 设置三语义 ============
st, s0 = call("GET", "/settings")
check("bug001", "R1.0 基线全新(三字段全空)", st == 200 and s0["llm"]["base_url"] is None
      and s0["llm"]["model"] is None and s0["llm"]["api_key"] is None, json.dumps(s0["llm"], ensure_ascii=False))

st, _ = call("PUT", "/settings", {"llm": {"base_url": "http://api.reg-a.test/v2", "model": "reg-model-a", "api_key": "sk-reg-secret-a"}})
st, s1 = call("GET", "/settings")
check("bug001", "R1.1 三项齐填全保存", st == 200 and s1["llm"]["base_url"] == "http://api.reg-a.test/v2"
      and s1["llm"]["model"] == "reg-model-a" and s1["llm"]["api_key"], json.dumps(s1["llm"], ensure_ascii=False))
check("bug001", "R1.1b 密钥掩码不回显明文", "sk-reg-secret-a" not in json.dumps(s1)
      and "****" in (s1["llm"]["api_key"] or ""), repr(s1["llm"]["api_key"]))

# 核心回归：只改一项
st, _ = call("PUT", "/settings", {"llm": {"base_url": "http://api.reg-b.test/v4"}})
st, s2 = call("GET", "/settings")
check("bug001", "R1.2 只改 base_url：model 不丢", st == 200 and s2["llm"]["model"] == "reg-model-a", repr(s2["llm"]["model"]))
check("bug001", "R1.2b 只改 base_url：api_key 不丢", s2["llm"]["api_key"] not in (None, ""), repr(s2["llm"]["api_key"]))
check("bug001", "R1.2c base_url 已更新", s2["llm"]["base_url"] == "http://api.reg-b.test/v4", repr(s2["llm"]["base_url"]))

st, _ = call("PUT", "/settings", {"llm": {"api_key": "sk-reg-secret-b"}})
st, s3 = call("GET", "/settings")
check("bug001", "R1.3 只换密钥：base_url/model 保持", st == 200 and s3["llm"]["base_url"] == "http://api.reg-b.test/v4"
      and s3["llm"]["model"] == "reg-model-a", json.dumps(s3["llm"], ensure_ascii=False))
check("bug001", "R1.3b 新密钥生效且掩码", "sk-reg-secret-b" not in json.dumps(s3) and s3["llm"]["api_key"], repr(s3["llm"]["api_key"]))

st, _ = call("PUT", "/settings", {"llm": {"model": None}})
st, s4 = call("GET", "/settings")
check("bug001", "R1.4 显式 null 清除 model", st == 200 and s4["llm"]["model"] is None, repr(s4["llm"]["model"]))
check("bug001", "R1.4b 清除 model 不波及其他", s4["llm"]["base_url"] == "http://api.reg-b.test/v4"
      and s4["llm"]["api_key"] not in (None, ""), json.dumps(s4["llm"], ensure_ascii=False))

st, _ = call("PUT", "/settings", {})
st, s5 = call("GET", "/settings")
check("bug001", "R1.5 空对象 no-op 不清数据", st == 200 and s5["llm"]["base_url"] == "http://api.reg-b.test/v4"
      and s5["llm"]["api_key"] not in (None, ""), json.dumps(s5["llm"], ensure_ascii=False))

st, _ = call("PUT", "/settings", {"llm": {}})
st, s5b = call("GET", "/settings")
check("bug001", "R1.5b 空 llm 节 no-op", st == 200 and s5b["llm"]["api_key"] not in (None, ""), repr(s5b["llm"]["api_key"]))

# embed 节同语义 + 跨节隔离
st, _ = call("PUT", "/settings", {"embed": {"base_url": "http://emb.reg.test", "model": "emb-m", "api_key": "sk-emb-secret"}})
st, _ = call("PUT", "/settings", {"embed": {"base_url": "http://emb.reg2.test"}})
st, s6 = call("GET", "/settings")
check("bug001", "R1.6 embed 只改一项其余保持", st == 200 and s6["embed"]["model"] == "emb-m"
      and s6["embed"]["api_key"] not in (None, "") and s6["embed"]["base_url"] == "http://emb.reg2.test",
      json.dumps(s6["embed"], ensure_ascii=False))
check("bug001", "R1.6b embed 修改不波及 llm 节", s6["llm"]["base_url"] == "http://api.reg-b.test/v4"
      and s6["llm"]["model"] is None and s6["llm"]["api_key"] not in (None, ""), json.dumps(s6["llm"], ensure_ascii=False))

# DB 层：密钥 Fernet 密文
try:
    conn = db_readonly()
    rows = conn.execute("SELECT key, value FROM settings WHERE key LIKE '%api_key%' OR key LIKE '%llm%' OR key LIKE '%embed%'").fetchall()
    blob = json.dumps(rows, ensure_ascii=False)
    check("bug001", "R1.7 DB 无明文密钥", "sk-reg-secret" not in blob and "sk-emb-secret" not in blob, blob[:200])
    gaaa = any("gAAAAAB" in str(v) for _, v in rows)
    check("bug001", "R1.7b DB 存 Fernet 密文", gaaa, f"rows={len(rows)}")
    conn.close()
except Exception as e:
    check("bug001", "R1.7 DB 检查", False, repr(e))

# 日志层：无明文
try:
    with open(LOG, encoding="utf-8", errors="replace") as f:
        logtxt = f.read()
    check("bug001", "R1.8 日志零明文密钥", "sk-reg-secret" not in logtxt and "sk-emb-secret" not in logtxt, f"loglen={len(logtxt)}")
except Exception as e:
    check("bug001", "R1.8 日志检查", False, repr(e))

# ============ BUG-003 幂等并发 ============
body, ctype = multipart({"name": "回归幂等书-A"}, "file", TX)
H = {"Idempotency-Key": "reg-idem-001"}
st1, r1 = call("POST", "/studies", raw_body=body, content_type=ctype, headers=H)
body2, ctype2 = multipart({"name": "回归幂等书-A"}, "file", TX)
st2, r2 = call("POST", "/studies", raw_body=body2, content_type=ctype2, headers=H)
id1 = (r1.get("study") or r1).get("id") if isinstance(r1, dict) else None
id2 = (r2.get("study") or r2).get("id") if isinstance(r2, dict) else None
check("bug003", "R3.1 同键两次同书", st1 in (200, 201) and st2 in (200, 201) and id1 == id2 and id1 is not None,
      f"status={st1}/{st2} id1={id1} id2={id2} keys={list(r1.keys())[:6]} created1={r1.get('created')} created2={r2.get('created')}")

# 并发 5 线程同键
body_c, ctype_c = multipart({"name": "回归幂等书-B"}, "file", TX)
HC = {"Idempotency-Key": "reg-idem-002"}
def fire(_):
    b, ct = multipart({"name": "回归幂等书-B"}, "file", TX)
    return call("POST", "/studies", raw_body=b, content_type=ct, headers=HC)
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
    cres = list(ex.map(fire, range(5)))
ids = set()
statuses = []
for stx, rx in cres:
    statuses.append(stx)
    rid = (rx.get("study") or rx).get("id") if isinstance(rx, dict) else None
    ids.add(rid)
check("bug003", "R3.2 并发5连发全成功且同一书", all(s in (200, 201) for s in statuses) and len(ids) == 1 and None not in ids,
      f"statuses={statuses} ids={ids}")
BID = ids.pop() if ids else None

# 不同键不同书
body_d, ctype_d = multipart({"name": "回归幂等书-C"}, "file", TX)
stx, rx = call("POST", "/studies", raw_body=body_d, content_type=ctype_d, headers={"Idempotency-Key": "reg-idem-003"})
idc = (rx.get("study") or rx).get("id") if isinstance(rx, dict) else None
check("bug003", "R3.3 不同键正常建新书", stx in (200, 201) and idc not in (None, BID), f"id={idc}")

st, lst = call("GET", "/studies")
items = lst if isinstance(lst, list) else lst.get("items", lst.get("studies", []))
names = [x["name"] for x in items]
check("bug003", "R3.4 书架无重复书名", names.count("回归幂等书-A") == 1 and names.count("回归幂等书-B") == 1,
      f"A={names.count('回归幂等书-A')} B={names.count('回归幂等书-B')} C={names.count('回归幂等书-C')}")
try:
    conn = db_readonly()
    n = conn.execute("SELECT COUNT(*) FROM studies WHERE name LIKE '回归幂等书-%'").fetchone()[0]
    check("bug003", "R3.5 DB 层 3 键 3 书", n == 3, f"count={n}")
    conn.close()
except Exception as e:
    check("bug003", "R3.5 DB 检查", False, repr(e))

# ============ BUG-002 桩用量 ============
st, u0 = call("GET", "/usage")
scenes0 = {r["scene"]: r for r in (u0 if isinstance(u0, list) else u0.get("rows", []))}
print(f"[bug002] usage before: {json.dumps(u0, ensure_ascii=False)[:300]}")

# 导入 TX 书触发 outline 规划
body_i, ctype_i = multipart({"name": "回归用量书-TX01"}, "file", TX)
sti, ri = call("POST", "/studies", raw_body=body_i, content_type=ctype_i, headers={"Idempotency-Key": "reg-usage-001"})
SID = (ri.get("study") or ri).get("id")
check("bug002", "R2.1 导入成功", sti in (200, 201) and SID is not None, f"id={SID}")

# 轮询树就绪（桩规划完成）
deadline = time.time() + 40
tree = {}
ai_group = 0
while time.time() < deadline:
    stt, tree = call("GET", f"/studies/{SID}/knowledge")
    if stt == 200 and tree.get("nodes"):
        ai_group = sum(1 for n in tree["nodes"] if n.get("origin") == "ai_group")
        if ai_group > 0 and all(n.get("children") is not None for n in tree["nodes"][:1]):
            units = [n for n in tree["nodes"] if n.get("is_learning_unit") and not n.get("excluded")]
            if units:
                break
    time.sleep(1.0)
check("bug002", "R2.2 树就绪(含 AI 分组)", ai_group > 0, f"roots={len(tree.get('nodes', []))} ai_group={ai_group}")

st, u1 = call("GET", "/usage")
scenes1 = {r["scene"]: r for r in (u1 if isinstance(u1, list) else u1.get("rows", []))}
check("bug002", "R2.3 outline 场景入账(BUG-002核心)", "outline" in scenes1, f"scenes={sorted(scenes1.keys())}")

# 会话 + 提问（tutor 流式，修复前已入账，回归防劣化）
units = [n for n in tree["nodes"] if n.get("is_learning_unit") and not n.get("excluded")]
units.sort(key=lambda n: n.get("sort_order", 0))
KP = units[0]["id"]
stc, sess = call("POST", f"/studies/{SID}/sessions", {"kp_id": KP})
sid = sess["session"]["id"]
def sse(path, body=None):
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
opening = sse(f"/sessions/{sid}/opening")
chat = sse(f"/sessions/{sid}/chat", {"content": "什么是决策循环？"})
st, u2 = call("GET", "/usage")
scenes2 = {r["scene"]: r for r in (u2 if isinstance(u2, list) else u2.get("rows", []))}
check("bug002", "R2.4 tutor 场景仍入账(防劣化)", "tutor" in scenes2, f"scenes={sorted(scenes2.keys())} opening_len={len(opening)} chat_len={len(chat)}")

# 生成测验（complete 分支，BUG-002 核心）
stq, quiz = call("POST", f"/sessions/{sid}/quizzes")
st, u3 = call("GET", "/usage")
scenes3 = {r["scene"]: r for r in (u3 if isinstance(u3, list) else u3.get("rows", []))}
check("bug002", "R2.5 quiz 场景入账(BUG-002核心)", stq == 200 and "quiz" in scenes3,
      f"scenes={sorted(scenes3.keys())} quiz_status={stq}")
check("bug002", "R2.6 用量行结构完整(日期/场景/调用数)", all(set(r) >= {"date", "scene"} for r in
      (u3 if isinstance(u3, list) else u3.get("rows", []))), json.dumps(u3, ensure_ascii=False)[:200])

# ============ 汇总 ============
with open(os.path.join(ROOT, "qa", "V0.1", "logs", "reg", "api-regression.json"), "w", encoding="utf-8") as f:
    json.dump(RESULTS, f, ensure_ascii=False, indent=2)
fails = [o for o in OUT if not o[2]]
print(f"\n==== SUMMARY: {len(OUT) - len(fails)}/{len(OUT)} PASS, {len(fails)} FAIL ====")
for g, n, _, d in fails:
    print(f"FAIL [{g}] {n} | {d}")
print(f"STUDY_ID={SID} KP={KP}")
