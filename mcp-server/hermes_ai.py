#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Proxy AI rewrite calls to local Hermes WebUI.

Under PLATFORM_AUTH_REQUIRED, /api/md/inline-edit and /api/canvas/rewrite need
loopback HMAC (same signing key as Agent BFF). Cursor Present has no browser
cookie, so we sign with ~/.hermes/webui/.signing_key.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_HERMES_BASE = "http://127.0.0.1:8787"
TIMEOUT_S = 45.0
# Must pass platform_auth._valid_loopback_session_id (UUID or 12-hex).
DOCUMENT_EDITOR_LOOPBACK_SESSION_ID = "d0c0ed17-0000-4000-8000-000000000001"


def hermes_base() -> str:
    return (os.environ.get("HERMES_WEBUI_BASE") or DEFAULT_HERMES_BASE).rstrip("/")


def _signing_key() -> bytes | None:
    env = (os.environ.get("HERMES_SIGNING_KEY_FILE") or "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).expanduser())
    home = Path.home()
    state = (os.environ.get("HERMES_WEBUI_STATE_DIR") or "").strip()
    if state:
        candidates.append(Path(state).expanduser() / ".signing_key")
    hermes_home = (os.environ.get("HERMES_HOME") or "").strip()
    if hermes_home:
        candidates.append(Path(hermes_home).expanduser() / "webui" / ".signing_key")
    candidates.append(home / ".hermes" / "webui" / ".signing_key")
    candidates.append(home / ".hermes" / "webui-mvp" / ".signing_key")
    for p in candidates:
        try:
            if p.is_file():
                raw = p.read_bytes()
                if len(raw) >= 32:
                    return raw[:32]
        except OSError:
            continue
    return None


def _loopback_headers(session_id: str) -> dict[str, str]:
    key = _signing_key()
    headers = {"X-Hermes-Loopback": "1"}
    if not key:
        return headers
    ts = str(int(time.time() * 1000))
    msg = f"{session_id}|{ts}".encode("utf-8")
    sig = hmac.new(key, msg, hashlib.sha256).hexdigest()
    headers["X-Hermes-Loopback-Ts"] = ts
    headers["X-Hermes-Loopback-Sig"] = sig
    return headers


def _request(
    method: str,
    path: str,
    body: dict | None = None,
    timeout: float = TIMEOUT_S,
    *,
    loopback: bool = False,
) -> dict[str, Any]:
    url = hermes_base() + path
    headers = {"Accept": "application/json"}
    data = None
    if loopback:
        sid = DOCUMENT_EDITOR_LOOPBACK_SESSION_ID
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}session_id={urllib.parse.quote(sid)}"
        headers.update(_loopback_headers(sid))
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw or "{}")
            except json.JSONDecodeError:
                return {"ok": False, "error": f"non-json from Hermes: {raw[:200]}"}
            if isinstance(parsed, dict):
                return parsed
            return {"ok": True, "data": parsed}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        try:
            parsed = json.loads(err_body or "{}")
            if isinstance(parsed, dict):
                parsed.setdefault("ok", False)
                parsed.setdefault("error", f"HTTP {e.code}")
                return parsed
        except json.JSONDecodeError:
            pass
        return {"ok": False, "error": f"Hermes HTTP {e.code}: {err_body[:300]}"}
    except urllib.error.URLError as e:
        return {
            "ok": False,
            "error": f"Hermes unreachable at {hermes_base()}: {e.reason}. 请先启动 Hermes WebUI。",
        }
    except TimeoutError:
        return {"ok": False, "error": f"Hermes timeout after {timeout}s"}


def ai_status() -> dict[str, Any]:
    base = hermes_base()
    result = _request("GET", "/health", timeout=3.0)
    if result.get("error") and (
        "unreachable" in str(result.get("error"))
        or "timeout" in str(result.get("error")).lower()
        or str(result.get("error")).startswith("Hermes HTTP")
    ):
        return {"ok": False, "hermes_base": base, "error": result["error"]}
    # Hermes /health returns {"status":"ok", ...} (not necessarily ok:true)
    healthy = (
        result.get("ok") is True
        or result.get("status") in ("ok", "healthy", "up")
        or ("error" not in result and "status" in result)
    )
    if not healthy and result.get("ok") is False:
        return {"ok": False, "hermes_base": base, "error": result.get("error") or "Hermes unhealthy"}
    return {"ok": True, "hermes_base": base, "health": result}


def inline_edit(selection: str, instruction: str, model: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "selection": selection or "",
        "instruction": instruction or "",
    }
    if model:
        body["model"] = model
    result = _request("POST", "/api/md/inline-edit", body, loopback=True)
    if result.get("ok") is False:
        return result
    # normalize
    if "replacement" not in result and "text" in result:
        result["replacement"] = result["text"]
    result.setdefault("ok", True)
    return result


def rewrite(
    instruction: str,
    parts: list[dict],
    format: str = "md",
    model: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "instruction": instruction or "",
        "parts": parts or [],
        "format": (format or "md").lower(),
    }
    if model:
        body["model"] = model
    if session_id:
        body["session_id"] = session_id
    result = _request("POST", "/api/canvas/rewrite", body, loopback=True)
    if result.get("ok") is False:
        return result
    result.setdefault("ok", True)
    return result


def document_ai_rewrite(
    instruction: str,
    *,
    selection: str | None = None,
    parts: list[dict] | None = None,
    format: str = "md",
    model: str | None = None,
    file_path: str | None = None,
    apply: bool | None = None,
    replacement: str | None = None,
    ranges: list | None = None,
) -> dict[str, Any]:
    """MCP / shared entry: prefer parts rewrite, else selection inline-edit.

    When file_path is Office (docx/xlsx/pptx) and selection is set, apply via
    editor_sdk (WorkBuddy-style: prefer doc_replace_text ranges). Default
    apply=True for office paths; md/html never auto-write here.
    """
    # Office path → Hermes rewrite + SDK write-back (status checked inside office_ai
    # unless replacement is provided for apply-only).
    if file_path and (selection is not None or ranges):
        from pathlib import Path

        suf = Path(file_path).suffix.lower()
        if suf in (".docx", ".doc", ".xlsx", ".xls", ".csv", ".pptx", ".ppt"):
            from office_ai import office_ai_rewrite

            do_apply = True if apply is None else bool(apply)
            return office_ai_rewrite(
                file_path,
                selection or "",
                instruction,
                apply=do_apply,
                model=model,
                format=format if format in ("docx", "xlsx", "pptx") else None,
                replacement=replacement,
                ranges=ranges,
            )

    status = ai_status()
    if not status.get("ok"):
        return status

    fmt = (format or "md").lower()
    if parts:
        out = rewrite(instruction, parts, format=fmt, model=model)
    elif selection is not None:
        out = inline_edit(selection, instruction, model=model)
    else:
        return {"ok": False, "error": "provide selection or parts"}
    if file_path:
        out["file_path"] = file_path
    return out
