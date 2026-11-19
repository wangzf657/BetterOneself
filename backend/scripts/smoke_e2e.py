"""真实 LLM 冒烟:导入→拆解→讲解→测验全链(需 backend/.env 配置真 key 后手动跑)。

用法:cd backend && uv run python scripts/smoke_e2e.py
不进 CI;验证提示词与真实模型交互质量,结果人工评估。
"""

import io
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from sqlalchemy import create_engine  # noqa: E402

from app.db import create_all, set_engine  # noqa: E402

DATA = BACKEND / "data" / "smoke"
DATA.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DATA / 'smoke.db'}", connect_args={"check_same_thread": False}
)
create_all(engine)
set_engine(engine)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

MD = """# Rust 所有权

所有权是 Rust 最核心的概念,编译器在编译时检查。

## 移动语义

将值赋给另一个变量时所有权移动,原变量失效,避免双重释放。

## 借用

引用不取得所有权;同一时刻可以有多个不可变引用或一个可变引用。
"""


def main() -> None:
    cfg_ok = bool(_has_key())
    print(f"[smoke] LLM key 配置: {cfg_ok}")
    with TestClient(app) as c:
        study = c.post("/api/studies", json={"name": "冒烟-Rust", "goal": "验证真实链路"}).json()
        r = c.post(
            f"/api/studies/{study['id']}/sources",
            files={"file": ("rust.md", io.BytesIO(MD.encode()), "text/markdown")},
        )
        sid = r.json()["id"]
        detail = c.get(f"/api/sources/{sid}").json()
        print(f"[smoke] 解析: {detail['parse_status']}, 切片 {len(detail['chunks'])}")

        tree = c.get(f"/api/studies/{study['id']}/knowledge").json()
        print("[smoke] 知识点树:")
        print(json.dumps(tree, ensure_ascii=False, indent=2)[:1200])
        kp = _first_leaf(tree)
        if kp is None:
            print("[smoke] 未拆出知识点,中止")
            return

        session = c.post(
            f"/api/studies/{study['id']}/sessions", json={"kp_id": kp["id"]}
        ).json()
        print("[smoke] 讲解(stub=off, 真实模型,节流):")
        with c.stream(
            "POST", f"/api/sessions/{session['id']}/chat", json={"content": "用一句话解释移动语义"}
        ) as resp:
            text = "".join(
                line[6:] for line in resp.iter_lines() if line.startswith("data: ")
            )
        print(text[:600])

        quizzes = c.post(f"/api/sessions/{session['id']}/quizzes").json()
        print(f"[smoke] 出题 {len(quizzes)} 道;第一题:{quizzes[0]['question'][:80]}")


def _first_leaf(nodes):
    for n in nodes:
        if not n["children"]:
            return n
        hit = _first_leaf(n["children"])
        if hit:
            return hit
    return None


def _has_key() -> bool:
    from app.config import get_config

    return bool(get_config().llm_api_key)


if __name__ == "__main__":
    main()
