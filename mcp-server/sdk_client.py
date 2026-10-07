#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTTP JSON-RPC client for local editor_sdk MCP endpoint (POST /mcp)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

DEFAULT_PORT = int(os.environ.get("EDITOR_SDK_PORT", "39099") or "39099")
PORT_SCAN_COUNT = 10
DISCOVERY_TIMEOUT = 2
TOKEN = os.environ.get("EDITOR_SDK_TOKEN", "").strip()

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_ENDPOINT: str | None = None
_RPC_ID = 0


class SdkError(RuntimeError):
    """editor_sdk call failed."""


def _endpoint(port: int | str) -> str:
    return f"http://127.0.0.1:{port}/mcp"


def _next_id() -> int:
    global _RPC_ID
    _RPC_ID += 1
    return _RPC_ID


def _request(endpoint: str, method: str, params: dict | None = None, timeout: float = 60) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": _next_id(),
        "method": method,
        "params": params or {},
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
    with _OPENER.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def discover_endpoint(force: bool = False) -> str:
    """Find a live editor_sdk /mcp endpoint; cache it."""
    global _ENDPOINT
    if _ENDPOINT and not force:
        return _ENDPOINT

    configured = os.environ.get("EDITOR_SDK_PORT", "").strip()
    if configured:
        _ENDPOINT = _endpoint(configured)
        return _ENDPOINT

    last = DEFAULT_PORT + PORT_SCAN_COUNT - 1
    for port in range(DEFAULT_PORT, DEFAULT_PORT + PORT_SCAN_COUNT):
        endpoint = _endpoint(port)
        try:
            obj = _request(endpoint, "tools/list", timeout=DISCOVERY_TIMEOUT)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise SdkError("401 unauthorized: set EDITOR_SDK_TOKEN") from e
            continue
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError, OSError):
            continue
        result = obj.get("result") if isinstance(obj, dict) else None
        if (
            isinstance(obj, dict)
            and obj.get("jsonrpc") == "2.0"
            and isinstance(result, dict)
            and isinstance(result.get("tools"), list)
        ):
            _ENDPOINT = endpoint
            return _ENDPOINT

    raise SdkError(
        f"editor_sdk not reachable on ports {DEFAULT_PORT}-{last}; "
        "start it or set EDITOR_SDK_BIN / EDITOR_SDK_PORT"
    )


def reset_endpoint() -> None:
    global _ENDPOINT
    _ENDPOINT = None


def rpc(method: str, params: dict | None = None, timeout: float = 120) -> Any:
    endpoint = discover_endpoint()
    try:
        obj = _request(endpoint, method, params, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise SdkError("401 unauthorized: set EDITOR_SDK_TOKEN") from e
        raise SdkError(f"HTTP {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        reset_endpoint()
        raise SdkError(f"connect failed ({endpoint}): {e.reason}") from e
    except TimeoutError as e:
        raise SdkError(f"timeout ({endpoint}): {e}") from e
    except json.JSONDecodeError as e:
        raise SdkError(f"bad JSON from {endpoint}: {e}") from e

    if obj.get("error"):
        err = obj["error"]
        raise SdkError(f"JSON-RPC {err.get('code')}: {err.get('message')}")
    return obj.get("result") or {}


def tools_list() -> list[dict]:
    return list(rpc("tools/list").get("tools") or [])


def _parse_file_id_from_text(text: str) -> str | None:
    import re

    m = re.search(r"file_id=([A-Za-z0-9_\-]+)", text or "")
    return m.group(1) if m else None


def tool_call(name: str, arguments: dict | None = None, timeout: float = 180) -> Any:
    result = rpc("tools/call", {"name": name, "arguments": arguments or {}}, timeout=timeout)
    if not isinstance(result, dict):
        return result

    texts = [
        c.get("text", "")
        for c in (result.get("content") or [])
        if isinstance(c, dict) and c.get("type") == "text"
    ]
    joined = "\n".join(texts) if texts else ""

    # Prefer structured JSON body when present.
    parsed: dict | None = None
    if joined:
        try:
            obj = json.loads(joined)
            if isinstance(obj, dict):
                parsed = obj
        except json.JSONDecodeError:
            parsed = None

    out: dict = {}
    # Top-level MCP result fields (create_doc/open_file often put file_id here).
    for key in ("file_id", "file_path", "file_type", "ok", "error", "message"):
        if key in result and result[key] is not None:
            out[key] = result[key]
    if parsed:
        out.update(parsed)
    elif joined:
        out["text"] = joined
        fid = _parse_file_id_from_text(joined)
        if fid and "file_id" not in out:
            out["file_id"] = fid
        # Also pull file_path=... from plain text if present.
        import re

        pm = re.search(r"file_path=([^\s,]+)", joined)
        if pm and "file_path" not in out:
            out["file_path"] = pm.group(1)

    # Preserve non-content extras (sheet data, etc.)
    for key, value in result.items():
        if key in ("content", "isError") or key in out:
            continue
        out[key] = value

    if out:
        return out
    return result


def is_alive() -> bool:
    try:
        discover_endpoint(force=True)
        tools_list()
        return True
    except Exception:
        return False
