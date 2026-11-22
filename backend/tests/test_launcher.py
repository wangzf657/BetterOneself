"""launcher 端口探测与实例判定单测（技术方案 §14.3）。"""

from __future__ import annotations

import http.server
import socket
import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from app.launcher import _find_free_port, _looks_like_our_app, _port_busy

_HOST = "127.0.0.1"


@contextmanager
def _stub_server(status: int) -> Iterator[int]:
    """起一个对任意 GET 返回固定状态码的临时 HTTP 服务，yield 端口。"""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(status)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    with socketserver.ThreadingTCPServer((_HOST, 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()


def _closed_port() -> int:
    """取一个当前无监听的端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((_HOST, 0))
        return s.getsockname()[1]


def test_port_busy_false_when_free() -> None:
    assert _port_busy(_HOST, _closed_port()) is False


def test_port_busy_true_when_listening() -> None:
    with _stub_server(200) as port:
        assert _port_busy(_HOST, port) is True


def test_find_free_port_returns_free_port() -> None:
    port = _find_free_port()
    assert _port_busy(_HOST, port) is False


def test_looks_like_our_app_true_on_200() -> None:
    with _stub_server(200) as port:
        assert _looks_like_our_app(_HOST, port) is True


def test_looks_like_our_app_false_on_404() -> None:
    with _stub_server(404) as port:
        assert _looks_like_our_app(_HOST, port) is False


def test_looks_like_our_app_false_without_listener() -> None:
    assert _looks_like_our_app(_HOST, _closed_port()) is False
