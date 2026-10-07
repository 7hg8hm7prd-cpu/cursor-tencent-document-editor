#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local WYSIWYG preview/edit server for .md / .html (WorkBuddy present_files analogue)."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from bridge import _abs, _html_to_md, _md_to_html, detect_format
from hermes_ai import ai_status, inline_edit, rewrite
from office_ai import office_ai_rewrite
from sdk_proxy import inject_js_bytes, proxy_sdk_request

DEFAULT_PORT = int(os.environ.get("DOCUMENT_PREVIEW_PORT", "39110") or "39110")
_PORT: int | None = None
_LOCK = threading.Lock()


UI_PATH = Path(__file__).resolve().parent / "present_ui.html"


def _load_editor_html() -> bytes:
    if UI_PATH.is_file():
        return UI_PATH.read_bytes()
    return b"<html><body>present_ui.html missing</body></html>"


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except OSError:
            return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: Any) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, data, "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/health":
            return self._json(200, {"ok": True, "service": "document-present"})
        if parsed.path == "/api/ai/status":
            st = ai_status()
            return self._json(200 if st.get("ok") else 503, st)
        # WorkBuddy-style: HTML on present port, assets on editor_sdk (:39099)
        if parsed.path == "/sdk-proxy/__hermes_mqq_inject.js":
            return self._send(200, inject_js_bytes(), "application/javascript; charset=utf-8")
        if parsed.path == "/office-frame":
            doc_type = (qs.get("type") or ["doc"])[0]
            if doc_type not in ("doc", "sheet", "slide", "pdf"):
                return self._json(400, {"ok": False, "error": f"bad type: {doc_type}"})
            # Forward all query params except type to SDK pc.html
            pairs = []
            for k, vals in qs.items():
                if k == "type":
                    continue
                for v in vals:
                    pairs.append((k, v))
            q = urllib.parse.urlencode(pairs)
            upstream = f"/static/{doc_type}/pc.html" + (f"?{q}" if q else "")
            out = proxy_sdk_request(
                "GET",
                upstream,
                headers={k: v for k, v in self.headers.items()},
                prepare_html=True,
            )
            return self._send(
                int(out.get("status") or 502),
                out.get("body") or b"",
                str(out.get("content_type") or "text/html; charset=utf-8"),
            )
        if parsed.path.startswith("/sdk-proxy/"):
            # Legacy path: still prepare HTML with absolute SDK asset URLs
            upstream = parsed.path[len("/sdk-proxy") :] or "/"
            if parsed.query:
                upstream = upstream + "?" + parsed.query
            is_html = upstream.split("?", 1)[0].endswith(".html")
            out = proxy_sdk_request(
                "GET",
                upstream,
                headers={k: v for k, v in self.headers.items()},
                prepare_html=is_html,
            )
            return self._send(
                int(out.get("status") or 502),
                out.get("body") or b"",
                str(out.get("content_type") or "application/octet-stream"),
            )
        if parsed.path in ("/", "/edit"):
            self._send(200, _load_editor_html(), "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/media/"):
            # /media/<urlencoded abs path>
            rel = parsed.path[len("/media/"):]
            try:
                target = _abs(urllib.parse.unquote(rel))
                if not target.is_file():
                    return self._json(404, {"ok": False, "error": "media not found"})
                data = target.read_bytes()
                ctype = "application/octet-stream"
                suf = target.suffix.lower()
                if suf in (".png",):
                    ctype = "image/png"
                elif suf in (".jpg", ".jpeg"):
                    ctype = "image/jpeg"
                elif suf == ".gif":
                    ctype = "image/gif"
                elif suf == ".webp":
                    ctype = "image/webp"
                elif suf == ".svg":
                    ctype = "image/svg+xml"
                return self._send(200, data, ctype)
            except OSError as e:
                return self._json(500, {"ok": False, "error": str(e)})
        if parsed.path == "/api/content":
            path = (qs.get("path") or [""])[0]
            try:
                p = _abs(path)
                if not p.is_file():
                    return self._json(404, {"ok": False, "error": f"not found: {p}"})
                fmt = detect_format(p)
                if fmt not in ("md", "html"):
                    return self._json(400, {"ok": False, "error": f"present UI only for md/html, got {fmt}"})
                content = p.read_text(encoding="utf-8", errors="replace")
                html_body = _md_to_html(content) if fmt == "md" else content
                return self._json(
                    200,
                    {
                        "ok": True,
                        "path": str(p),
                        "format": fmt,
                        "content": content,
                        "html": html_body,
                    },
                )
            except OSError as e:
                return self._json(500, {"ok": False, "error": str(e)})
        self._json(404, {"ok": False, "error": "not found"})


    def _parse_multipart(self) -> dict[str, Any] | None:
        """Minimal multipart/form-data parser (no cgi; Python 3.13+ safe)."""
        ctype = self.headers.get("Content-Type") or ""
        if "multipart/form-data" not in ctype:
            return None
        m = re.search(r"boundary=([^;]+)", ctype, flags=re.I)
        if not m:
            return None
        boundary = m.group(1).strip().strip('"').encode("utf-8")
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        parts: dict[str, Any] = {}
        for chunk in raw.split(b"--" + boundary):
            if not chunk or chunk in (b"--\r\n", b"--", b"--\n"):
                continue
            if chunk.startswith(b"\r\n"):
                chunk = chunk[2:]
            if chunk.endswith(b"\r\n"):
                chunk = chunk[:-2]
            if b"\r\n\r\n" not in chunk:
                continue
            header_blob, body = chunk.split(b"\r\n\r\n", 1)
            if body.endswith(b"\r\n"):
                body = body[:-2]
            headers = header_blob.decode("utf-8", errors="replace")
            name_m = re.search(r'name="([^"]+)"', headers)
            if not name_m:
                continue
            name = name_m.group(1)
            file_m = re.search(r'filename="([^"]*)"', headers)
            if file_m is not None:
                parts[name] = {"filename": file_m.group(1), "data": body}
            else:
                parts[name] = body.decode("utf-8", errors="replace")
        return parts

    def _handle_upload(self):
        parts = self._parse_multipart()
        if parts is None:
            return self._json(400, {"ok": False, "error": "expected multipart/form-data"})
        file_item = parts.get("file")
        doc_path = parts.get("path") or ""
        if not isinstance(file_item, dict) or "data" not in file_item:
            return self._json(400, {"ok": False, "error": "missing file"})
        try:
            base = _abs(str(doc_path)).parent if doc_path else Path.cwd()
            base.mkdir(parents=True, exist_ok=True)
            name = Path(file_item.get("filename") or "upload.bin").name
            name = "".join(c if c.isalnum() or c in "._-+" else "_" for c in name) or "upload.bin"
            dest = base / name
            data = file_item["data"]
            dest.write_bytes(data)
            media_url = "/media/" + urllib.parse.quote(str(dest), safe="")
            return self._json(
                200,
                {
                    "ok": True,
                    "path": str(dest),
                    "name": name,
                    "url": media_url,
                    "bytes": len(data),
                },
            )
        except OSError as e:
            return self._json(500, {"ok": False, "error": str(e)})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/upload":
            return self._handle_upload()
        # Proxy SDK MCP / other POSTs (guest may call via rewritten paths)
        if parsed.path.startswith("/sdk-proxy/"):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            upstream = parsed.path[len("/sdk-proxy") :] or "/"
            if parsed.query:
                upstream = upstream + "?" + parsed.query
            out = proxy_sdk_request(
                "POST",
                upstream,
                body=raw,
                headers={k: v for k, v in self.headers.items()},
            )
            return self._send(
                int(out.get("status") or 502),
                out.get("body") or b"",
                str(out.get("content_type") or "application/octet-stream"),
            )
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return self._json(400, {"ok": False, "error": "bad json"})

        if parsed.path == "/api/render":
            fmt = (body.get("format") or "md").lower()
            content = body.get("content") or ""
            if fmt == "md":
                return self._json(200, {"ok": True, "html": _md_to_html(content)})
            return self._json(200, {"ok": True, "html": content})

        if parsed.path == "/api/save":
            path = body.get("path") or ""
            try:
                p = _abs(path)
                fmt = detect_format(p, body.get("format"))
                if fmt not in ("md", "html"):
                    return self._json(400, {"ok": False, "error": f"cannot save format {fmt} via present UI"})
                if fmt == "md":
                    if body.get("content") is not None:
                        text = str(body.get("content"))
                    else:
                        text = _html_to_md(str(body.get("html") or ""))
                else:
                    text = str(body.get("content") if body.get("content") is not None else body.get("html") or "")
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
                return self._json(200, {"ok": True, "path": str(p), "bytes": len(text.encode("utf-8"))})
            except OSError as e:
                return self._json(500, {"ok": False, "error": str(e)})

        if parsed.path == "/api/ai/inline-edit":
            out = inline_edit(
                str(body.get("selection") or ""),
                str(body.get("instruction") or ""),
                body.get("model"),
            )
            return self._json(200 if out.get("ok") is not False else 502, out)

        if parsed.path == "/api/ai/rewrite":
            parts = body.get("parts") or []
            if not isinstance(parts, list):
                return self._json(400, {"ok": False, "error": "parts must be a list"})
            out = rewrite(
                str(body.get("instruction") or ""),
                parts,
                format=str(body.get("format") or "md"),
                model=body.get("model"),
                session_id=body.get("session_id"),
            )
            return self._json(200 if out.get("ok") is not False else 502, out)

        if parsed.path == "/api/ai/office-apply":
            apply = body.get("apply")
            if apply is None:
                apply = True
            repl = body.get("replacement")
            ranges = body.get("ranges")
            if not isinstance(ranges, list):
                ranges = None
            out = office_ai_rewrite(
                str(body.get("file_path") or ""),
                str(body.get("selection") or ""),
                str(body.get("instruction") or ""),
                apply=bool(apply),
                model=body.get("model"),
                format=body.get("format"),
                replacement=str(repl) if repl is not None else None,
                ranges=ranges,
                file_id=body.get("file_id"),
            )
            return self._json(200 if out.get("ok") is not False else 502, out)

        self._json(404, {"ok": False, "error": "not found"})


def serve_forever(port: int | None = None) -> None:
    """Block and serve (used by preview_daemon)."""
    want = int(port or DEFAULT_PORT)
    server = ThreadingHTTPServer(("127.0.0.1", want), Handler)
    server.serve_forever()


def ensure_preview_server(port: int | None = None) -> dict:
    """Start the present/edit HTTP server if needed (detached process)."""
    global _PORT
    want = int(port or DEFAULT_PORT)
    with _LOCK:
        if _port_open(want):
            _PORT = want
            return {"ok": True, "started": False, "port": want, "base": f"http://127.0.0.1:{want}"}

        daemon = Path(__file__).resolve().parent / "preview_daemon.py"
        log_dir = Path(os.environ.get("DOCUMENT_PREVIEW_LOG_DIR") or "/tmp/document_preview_logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "preview_daemon.log"
        env = os.environ.copy()
        env["DOCUMENT_PREVIEW_PORT"] = str(want)
        try:
            with open(log_path, "ab") as logf:
                subprocess.Popen(
                    [sys.executable, str(daemon)],
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    env=env,
                )
        except OSError as e:
            return {"ok": False, "error": f"spawn preview_daemon failed: {e}"}

        import time

        deadline = time.time() + 5.0
        while time.time() < deadline:
            time.sleep(0.15)
            if _port_open(want):
                _PORT = want
                return {
                    "ok": True,
                    "started": True,
                    "port": want,
                    "base": f"http://127.0.0.1:{want}",
                    "log": str(log_path),
                }
        return {
            "ok": False,
            "error": f"preview daemon not ready on {want}; see {log_path}",
        }


def _open_in_cursor_simple_browser(url: str) -> bool:
    """Best-effort: open URL inside Cursor Simple Browser (IDE panel)."""
    # vscode.simple-browser deep link — Cursor inherits this command id.
    encoded = urllib.parse.quote(url, safe="")
    deep = f"vscode://vscode.simple-browser/show?url={encoded}"
    cursor_bin = shutil.which("cursor") or "/Applications/Cursor.app/Contents/Resources/app/bin/cursor"
    candidates = [
        [cursor_bin, "--open-url", deep],
        [cursor_bin, deep],
        ["open", "-a", "Cursor", deep],
    ]
    for cmd in candidates:
        try:
            if not cmd[0] or (cmd[0].endswith("cursor") and not Path(cmd[0]).exists() and not shutil.which(cmd[0])):
                continue
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            continue
    return False


def present_url(
    file_path: str,
    open_browser: bool = True,
    target: str | None = None,
) -> dict:
    path = _abs(file_path)
    if not path.is_file():
        return {"ok": False, "error": f"file not found: {path}"}
    fmt = detect_format(path)
    # Office / PDF → editor_sdk visual static editor (WorkBuddy present_files)
    if fmt in ("docx", "pptx", "xlsx", "pdf"):
        from sdk_preview import present_office

        mode = "readonly" if fmt == "pdf" else "edit"
        return present_office(
            str(path),
            open_browser=open_browser,
            target=target,
            mode=mode,
        )
    if fmt not in ("md", "html"):
        return {
            "ok": False,
            "error": f"document_present unsupported format: {fmt}",
            "format": fmt,
        }
    status = ensure_preview_server()
    if not status.get("ok"):
        return status
    base = status["base"]
    url = f"{base}/edit?path={urllib.parse.quote(str(path))}&format={fmt}"
    opened = False
    opened_where = "none"
    # Default: prefer Cursor IDE Simple Browser, then system browser.
    want = (target or os.environ.get("DOCUMENT_PREVIEW_TARGET") or "cursor").lower()
    if open_browser and os.environ.get("DOCUMENT_PREVIEW_NO_OPEN") != "1":
        if want in ("cursor", "ide", "simple-browser", "auto"):
            if _open_in_cursor_simple_browser(url):
                opened = True
                opened_where = "cursor-simple-browser"
        if not opened and want in ("browser", "system", "auto", "cursor", "ide", "simple-browser"):
            # Fallback / explicit system browser
            if want == "browser" or want == "system" or not opened:
                try:
                    subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    opened = True
                    opened_where = "system-browser"
                except OSError:
                    pass
    return {
        "ok": True,
        "format": fmt,
        "file_path": str(path),
        "url": url,
        "port": status["port"],
        "opened_browser": opened,
        "opened_where": opened_where,
        "how_to_open_in_cursor": (
            "Command Palette (Cmd+Shift+P) → “Simple Browser: Show” → paste the url"
        ),
        "note": "Prefer Cursor Simple Browser for in-IDE preview; Cmd/Ctrl+S saves to disk.",
    }
