"""一键启动器：打包 exe 的入口（技术方案 §14.3），开发时也可 `uv run python -m app.launcher`。

双击 exe：起服务 → 自动打开浏览器进应用；端口被占用时判定是否已有实例，
是我们自己则直接开浏览器指向它，否则换空闲端口。关掉控制台窗口即停止服务。
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser

import httpx
import uvicorn

from app.core.config import get_config
from app.main import app  # 顶层 import：PyInstaller 以此为根完成全量分析

_READY_TIMEOUT_SECONDS = 30.0


def _port_busy(host: str, port: int) -> bool:
    """以客户端视角探测：有进程在监听即视为占用。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _looks_like_our_app(host: str, port: int) -> bool:
    # shortcut: 实例判定仅凭 /api/studies 返回 200，多服务共端口误判场景升级
    try:
        resp = httpx.get(f"http://{host}:{port}/api/studies", timeout=1.0)
    except httpx.HTTPError:
        return False
    return resp.status_code == 200


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))  # shortcut: 绑定后关闭有理论竞态，单机自用可接受
        return int(s.getsockname()[1])


def _open_when_ready(host: str, port: int, url: str) -> None:
    deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if not _port_busy(host, port):
            time.sleep(0.25)
            continue
        webbrowser.open(url)
        return
    print(f"等待 {url} 就绪超时，未自动打开浏览器，请手动访问", flush=True)


def _browser_url(host: str, port: int) -> str:
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    return f"http://{host}:{port}"


def main() -> int:
    if sys.platform == "win32":
        import io

        for name in ("stdout", "stderr"):
            stream = getattr(sys, name)
            if isinstance(stream, io.TextIOWrapper):
                stream.reconfigure(encoding="utf-8", errors="replace")

    cfg = get_config()
    host, port = cfg.host, cfg.port
    if _port_busy(host, port):
        if _looks_like_our_app(host, port):
            print(f"检测到 BetterOneself 已在 {cfg.port} 端口运行，直接打开页面", flush=True)
            webbrowser.open(_browser_url(host, port))
            return 0
        port = _find_free_port()
        print(f"端口 {cfg.port} 被其他程序占用，改用空闲端口 {port}", flush=True)

    url = _browser_url(host, port)
    if os.environ.get("BO_NO_BROWSER") != "1":  # shortcut: 仅 V0.1 QA 冒烟需要，有编排需求时升级
        threading.Thread(target=_open_when_ready, args=(host, port, url), daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_config=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
