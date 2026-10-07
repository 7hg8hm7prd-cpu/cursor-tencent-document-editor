#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Proxy AI rewrite calls to local Hermes WebUI."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

DEFAULT_HERMES_BASE = "http://127.0.0.1:8787"
TIMEOUT_S = 45.0


def hermes_base() -> str:
    return (os.environ.get("HERMES_WEBUI_BASE") or DEFAULT_HERMES_BASE).rstrip("/")


def _request(
    method: str,
    path: str,
    body: dict | None = None,
    timeout: float = TIMEOUT_S,
) -> dict[str, Any]:
    url = hermes_base() + path
    data = None
    headers = {"Accept": "application/json"}
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
    result = _request("POST", "/api/md/inline-edit", body)
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
    result = _request("POST", "/api/canvas/rewrite", body)
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
) -> dict[str, Any]:
    """MCP / shared entry: prefer parts rewrite, else selection inline-edit."""
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
