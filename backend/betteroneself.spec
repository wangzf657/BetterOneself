# -*- mode: python ; coding: utf-8 -*-
"""BetterOneself 打包配置：PyInstaller onedir，双击 exe 即用（技术方案 §14、决策 #33）。

构建：cd backend && uv sync && uv run python scripts/build_exe.py
"""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# spec 内相对路径一律以 spec 所在目录（backend/）为基准
ROOT = SPECPATH

datas = [
    # 前端构建产物：冻结时 _mount_frontend 读 <资源>/frontend_dist
    (os.path.join(ROOT, "..", "frontend", "dist"), "frontend_dist"),
    # 启动迁移：run_migrations 读 BACKEND_DIR/alembic.ini 与 BACKEND_DIR/alembic
    (os.path.join(ROOT, "alembic.ini"), "."),
    (os.path.join(ROOT, "alembic"), "alembic"),
    # 三个 skill 的 prompt.md：PROMPT_PATH = Path(__file__).parent / "prompt.md"，按原相对路径放置零改动
    (os.path.join(ROOT, "app", "skills", "outline_planner", "prompt.md"), os.path.join("app", "skills", "outline_planner")),
    (os.path.join(ROOT, "app", "skills", "quiz", "prompt.md"), os.path.join("app", "skills", "quiz")),
    (os.path.join(ROOT, "app", "skills", "tutor", "prompt.md"), os.path.join("app", "skills", "tutor")),
]
# vec0.dll 必须与 sqlite_vec 模块同目录，否则 load_extension 失败
datas += collect_data_files("sqlite_vec")

hiddenimports = [
    # uvicorn 运行时按字符串惰性导入 loop/protocol/lifespan 子模块，静态分析收不齐
    m for m in collect_submodules("uvicorn") if not m.startswith("uvicorn.workers")
] + collect_submodules("openai")  # openai SDK 亦有惰性导入，防漏收

a = Analysis(
    [os.path.join(ROOT, "app", "launcher.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BetterOneself",
    console=True,  # 控制台可见是刻意的：日志可排障，关窗即停止服务（决策 #33）
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="BetterOneself",
)
