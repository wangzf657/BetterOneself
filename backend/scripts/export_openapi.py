"""导出 OpenAPI schema 供前端生成类型(frontend: pnpm gen:api)。"""

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app  # noqa: E402

target = BACKEND_ROOT.parent / "frontend" / "openapi.json"
target.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
print(f"written: {target}")
