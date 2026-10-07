#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transparent reverse proxy on the public editor_sdk port.

Host iframe still uses http://127.0.0.1:39099/... (local WorkBuddy URL).
Real editor_sdk listens on EDITOR_SDK_UPSTREAM_PORT (default 39101).

Critical: editor_sdk guest needs WebSocket to the same host. This proxy
tunnels Upgrade: websocket in addition to HTTP, and injects mqq + float AI
into pc.html only.
"""

from __future__ import annotations

import os
import select
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from sdk_client import DEFAULT_PORT

PUBLIC_PORT = int(os.environ.get("EDITOR_SDK_PORT") or DEFAULT_PORT or 39099)
UPSTREAM_PORT = int(os.environ.get("EDITOR_SDK_UPSTREAM_PORT") or "39101")
ROOT = Path(__file__).resolve().parent


def _inject_bundle() -> bytes:
    parts = [
        ROOT / "mqq_inject.js",
        ROOT / "float_toolbar_ai.js",
    ]
    chunks = [b"(function(){\n"]
    for p in parts:
        if p.is_file():
            chunks.append(p.read_bytes())
            chunks.append(b"\n;\n")
    chunks.append(b"})();\n")
    return b"".join(chunks)


def _prepare_html(html: bytes) -> bytes:
    if b"data-hermes-mqq" in html or b"hermes-tencent-doc-mqq" in html:
        return html
    tag = b'<script data-hermes-mqq="1">\n' + _inject_bundle() + b"\n</script>"
    lower = html.lower()
    idx = lower.find(b"<head")
    if idx >= 0:
        gt = html.find(b">", idx)
        if gt >= 0:
            return html[: gt + 1] + tag + html[gt + 1 :]
    return tag + html


def _upstream(method: str, path: str, body: bytes | None, headers: dict) -> tuple[int, dict, bytes]:
    url = f"http://127.0.0.1:{UPSTREAM_PORT}{path}"
    req_headers = {k: v for k, v in headers.items() if k.lower() not in ("host", "content-length")}
    data = body if method in ("POST", "PUT", "PATCH") else None
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            out_h = {k: v for k, v in resp.headers.items()}
            return int(resp.getcode() or 200), out_h, raw
    except urllib.error.HTTPError as e:
        raw = e.read() if e.fp else b""
        out_h = {k: v for k, v in (e.headers.items() if e.headers else [])}
        return int(e.code), out_h, raw
    except urllib.error.URLError as e:
        msg = f'{{"ok":false,"error":"upstream editor_sdk :{UPSTREAM_PORT} unreachable: {e.reason}"}}'
        return 502, {"Content-Type": "application/json"}, msg.encode("utf-8")


def _pipe(a: socket.socket, b: socket.socket) -> None:
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        try:
            b.shutdown(socket.SHUT_WR)
        except OSError:
            pass


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def _is_websocket(self) -> bool:
        return (self.headers.get("Upgrade") or "").lower() == "websocket"

    def _ws_tunnel(self) -> None:
        """Raw TCP tunnel after forwarding the client's Upgrade request upstream."""
        try:
            up = socket.create_connection(("127.0.0.1", UPSTREAM_PORT), timeout=15)
        except OSError as e:
            self.send_error(502, f"upstream ws connect failed: {e}")
            return

        # Rebuild request for upstream (headers already consumed from client)
        lines = [f"GET {self.path} HTTP/1.1"]
        for key, val in self.headers.items():
            if key.lower() == "host":
                val = f"127.0.0.1:{UPSTREAM_PORT}"
            lines.append(f"{key}: {val}")
        up.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1", errors="replace"))

        client = self.connection
        self.close_connection = True

        # Bidirectional copy (upstream response includes 101 + frames)
        t = threading.Thread(target=_pipe, args=(up, client), daemon=True)
        t.start()
        _pipe(client, up)
        t.join(timeout=1.0)
        try:
            up.close()
        except OSError:
            pass

    def _proxy(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        path = self.path
        code, headers, raw = _upstream(method, path, body, dict(self.headers))
        ctype = headers.get("Content-Type") or headers.get("content-type") or ""
        path_only = path.split("?", 1)[0]
        if "text/html" in ctype.lower() or path_only.endswith("pc.html"):
            raw = _prepare_html(raw)
            ctype = "text/html; charset=utf-8"
            headers["Content-Type"] = ctype
        self.send_response(code)
        skip = {
            "transfer-encoding",
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "upgrade",
            "content-encoding",
            "content-length",
        }
        for k, v in headers.items():
            if k.lower() in skip:
                continue
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self._is_websocket():
            return self._ws_tunnel()
        self._proxy("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._proxy("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._proxy("PUT")

    def do_HEAD(self) -> None:  # noqa: N802
        self._proxy("HEAD")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,HEAD,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except OSError:
            return False


def ensure_upstream_sdk() -> dict:
    if _port_open(UPSTREAM_PORT):
        return {"ok": True, "started": False, "port": UPSTREAM_PORT}
    env = os.environ.copy()
    env["EDITOR_SDK_PORT"] = str(UPSTREAM_PORT)
    ensure = ROOT / "ensure_sdk.py"
    try:
        subprocess.run(
            [sys.executable, str(ensure)],
            env=env,
            check=False,
            timeout=45,
            capture_output=True,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": str(e)}
    if _port_open(UPSTREAM_PORT):
        return {"ok": True, "started": True, "port": UPSTREAM_PORT}
    return {"ok": False, "error": f"upstream :{UPSTREAM_PORT} not ready"}


def serve_forever(port: int | None = None) -> None:
    want = int(port or PUBLIC_PORT)
    up = ensure_upstream_sdk()
    if not up.get("ok"):
        print(f"[sdk_port_proxy] upstream failed: {up}", file=sys.stderr)
    server = ThreadingHTTPServer(("127.0.0.1", want), Handler)
    print(
        f"[sdk_port_proxy] public=:{want} upstream=:{UPSTREAM_PORT} inject+ws",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    serve_forever()
