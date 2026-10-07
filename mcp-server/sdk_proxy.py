#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Office frame helper: inject WorkBuddy mqq while keeping SDK assets on :39099.

Why not full /sdk-proxy for the SPA?
  Guest uses location.host for some channels (WebSocket etc.). Serving the whole
  app through :39110 breaks load. Instead we only host the HTML on present port,
  point script/link/src at absolute editor_sdk URLs, and set editorSdkUrl=39099.
"""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from sdk_client import DEFAULT_PORT

INJECT_MARKER = b"hermes-tencent-doc-mqq"


def sdk_upstream_port() -> int:
    return int(os.environ.get("EDITOR_SDK_PORT") or DEFAULT_PORT or 39099)


def inject_js_bytes() -> bytes:
    path = Path(__file__).resolve().parent / "mqq_inject.js"
    return path.read_bytes()


def _inline_inject_tag() -> bytes:
    js = inject_js_bytes()
    # Keep as classic script so it runs before guest bundles.
    return b"<script data-hermes-mqq=\"1\">\n" + js + b"\n</script>"


def rewrite_assets_to_sdk_origin(html: bytes, sdk_port: int | None = None) -> bytes:
    """Rewrite root-absolute /static and /mcp to http://127.0.0.1:<sdk>/..."""
    port = int(sdk_port or sdk_upstream_port())
    origin = f"http://127.0.0.1:{port}".encode("utf-8")

    def repl_attr(m: re.Match[bytes]) -> bytes:
        attr, quote, url = m.group(1), m.group(2), m.group(3)
        if url.startswith(b"http://") or url.startswith(b"https://") or url.startswith(b"//"):
            return m.group(0)
        if url.startswith(b"/static/") or url.startswith(b"/mcp"):
            return attr + b"=" + quote + origin + url + quote
        return m.group(0)

    html = re.sub(
        rb'((?:src|href))=(["\'])(/[^"\']*)\2',
        repl_attr,
        html,
        flags=re.I,
    )
    # crossorigin=anonymous blocks classic scripts without CORS when host≠sdk
    html = re.sub(rb"\s+crossorigin=(['\"])anonymous\1", b"", html, flags=re.I)
    html = re.sub(rb"\s+crossorigin=(['\"])use-credentials\1", b"", html, flags=re.I)
    html = re.sub(rb"\s+crossorigin\b", b"", html, flags=re.I)
    return html


def inject_mqq_into_html(html: bytes, *, rewrite_assets: bool = True) -> bytes:
    if INJECT_MARKER in html or b"data-hermes-mqq" in html:
        if rewrite_assets:
            return rewrite_assets_to_sdk_origin(html)
        return html
    if rewrite_assets:
        html = rewrite_assets_to_sdk_origin(html)
    tag = _inline_inject_tag()
    lower = html.lower()
    idx = lower.find(b"<head")
    if idx >= 0:
        gt = html.find(b">", idx)
        if gt >= 0:
            return html[: gt + 1] + tag + html[gt + 1 :]
    idx = lower.find(b"<html")
    if idx >= 0:
        gt = html.find(b">", idx)
        if gt >= 0:
            return html[: gt + 1] + tag + html[gt + 1 :]
    return tag + html


def proxy_sdk_request(
    method: str,
    upstream_path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
    prepare_html: bool = False,
) -> dict[str, Any]:
    """Fetch from editor_sdk. upstream_path must start with /."""
    if not upstream_path.startswith("/"):
        upstream_path = "/" + upstream_path
    port = sdk_upstream_port()
    url = f"http://127.0.0.1:{port}{upstream_path}"
    req_headers = dict(headers or {})
    req_headers.pop("Host", None)
    req_headers.pop("host", None)
    data = body if method.upper() in ("POST", "PUT", "PATCH") else None
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type") or "application/octet-stream"
            code = resp.getcode() or 200
    except urllib.error.HTTPError as e:
        raw = e.read() if e.fp else b""
        ctype = e.headers.get("Content-Type") if e.headers else "text/plain"
        code = e.code
    except urllib.error.URLError as e:
        return {
            "ok": False,
            "status": 502,
            "content_type": "application/json; charset=utf-8",
            "body": (
                b'{"ok":false,"error":"editor_sdk upstream unreachable: '
                + str(e.reason).encode("utf-8", errors="replace")
                + b'"}'
            ),
        }

    is_html = "text/html" in (ctype or "").lower() or upstream_path.split("?", 1)[0].endswith(
        ".html"
    )
    if is_html and raw and prepare_html:
        raw = inject_mqq_into_html(raw, rewrite_assets=True)
        ctype = "text/html; charset=utf-8"

    return {
        "ok": True,
        "status": int(code),
        "content_type": ctype,
        "body": raw,
    }


def build_office_frame_url(
    file_path: str,
    *,
    preview_port: int,
    sdk_port: int | None = None,
    mode: str = "edit",
) -> str:
    """HTML hosted on present port; assets + API on editor_sdk port."""
    from sdk_preview import build_sdk_preview_url, sdk_doc_type

    path = Path(file_path).expanduser().resolve()
    doc_type = sdk_doc_type(path) or "doc"
    raw = build_sdk_preview_url(path, port=sdk_port or sdk_upstream_port(), mode=mode)
    # raw = http://127.0.0.1:39099/static/doc/pc.html?qs
    q = urllib.parse.urlparse(raw).query
    return (
        f"http://127.0.0.1:{int(preview_port)}/office-frame"
        f"?type={urllib.parse.quote(doc_type)}&{q}"
    )


def build_proxied_sdk_url(
    file_path: str,
    *,
    preview_port: int,
    sdk_port: int | None = None,
    mode: str = "edit",
) -> str:
    """Back-compat alias → office-frame (reliable load)."""
    return build_office_frame_url(
        file_path, preview_port=preview_port, sdk_port=sdk_port, mode=mode
    )
