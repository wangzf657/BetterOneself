"""构建 Windows 免安装文件夹（技术方案 §14）：先 pnpm build 前端，再 PyInstaller onedir。

用法：cd backend && uv sync && uv run python scripts/build_exe.py
产物：backend/dist/BetterOneself/（整文件夹拷贝即分发，双击 BetterOneself.exe）
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"


def build_frontend() -> None:
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        raise SystemExit("构建机需要 pnpm（仅构建期需要，用户机零依赖）")
    print("==> pnpm build（前端）")
    subprocess.run([pnpm, "run", "build"], cwd=FRONTEND_DIR, check=True)
    if not (FRONTEND_DIR / "dist" / "index.html").is_file():
        raise SystemExit("前端构建后仍无 frontend/dist/index.html")


def build_exe() -> None:
    build_frontend()
    print("==> PyInstaller onedir")
    import PyInstaller.__main__

    PyInstaller.__main__.run(
        [
            "--noconfirm",
            "--clean",
            f"--distpath={BACKEND_DIR / 'dist'}",
            f"--workpath={BACKEND_DIR / 'build'}",
            str(BACKEND_DIR / "betteroneself.spec"),
        ]
    )
    out = BACKEND_DIR / "dist" / "BetterOneself"
    print(f"==> 完成：{out}")
    print("    整个文件夹拷走即可分发；双击 BetterOneself.exe 运行。")


if __name__ == "__main__":
    try:
        build_exe()
    except subprocess.CalledProcessError as e:
        sys.exit(f"构建失败（退出码 {e.returncode}），见上方日志")
