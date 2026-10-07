#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build editor_sdk visual preview URLs (WorkBuddy present_files analogue).

The SDK HTTP server exposes:
  - /mcp              JSON-RPC tools (headless open/edit)
  - /static/{type}/pc.html?...  iframe-able WYSIWYG editor (doc/sheet/slide/pdf)

Visual present MUST use /static/...; open_file alone does not show UI.
"""

from __future__ import annotations

import hashlib
import os
import urllib.parse
from pathlib import Path
from typing import Any

from ensure_sdk import ensure_sdk
from sdk_client import DEFAULT_PORT

# Align with @tencent/tencent-docs-ai-engine buildPreviewUrl / URL_CONFIG_MAP
_TYPE_BY_EXT = {
    ".docx": "doc",
    ".doc": "doc",
    ".wps": "doc",
    ".wpt": "doc",
    ".dot": "doc",
    ".dotx": "doc",
    ".xlsx": "sheet",
    ".xls": "sheet",
    ".csv": "sheet",
    ".tsv": "sheet",
    ".xlt": "sheet",
    ".xltx": "sheet",
    ".pptx": "slide",
    ".ppt": "slide",
    ".pps": "slide",
    ".pot": "slide",
    ".potx": "slide",
    ".pdf": "pdf",
}

_URL_PARAMS = {
    "doc": {
        "edit": {
            "local_edit": "1",
            "client": "sdk_local",
            "mode": "edit",
            "toolbar": "show",
            "outline": "show",
            "statusbar": "show",
        },
        "readonly": {
            "local_edit": "1",
            "client": "sdk_local",
            "mode": "readonly",
            "toolbar": "hide",
            "outline": "show",
            "statusbar": "hide",
        },
    },
    "sheet": {
        "edit": {"local_edit": "1", "client": "sdk_local_pure", "mode": "edit"},
        "readonly": {
            "local_edit": "1",
            "client": "sdk_local_pure",
            "mode": "readonly",
        },
    },
    "slide": {
        "edit": {"local_edit": "1", "client": "sdk_local_wb", "hideTitlebar": "1"},
        "readonly": {"local_edit": "1", "client": "sdk_local_preview", "hideTitlebar": "1"},
    },
    "pdf": {
        "edit": {},
        "readonly": {},
    },
}


def sdk_doc_type(path: Path | str) -> str | None:
    ext = Path(path).suffix.lower()
    return _TYPE_BY_EXT.get(ext)


def build_sdk_preview_url(
    file_path: str | Path,
    *,
    port: int | str | None = None,
    mode: str = "edit",
) -> str:
    path = Path(file_path).expanduser().resolve()
    doc_type = sdk_doc_type(path)
    if not doc_type:
        raise ValueError(f"unsupported office extension: {path.suffix}")
    want_port = str(port or os.environ.get("EDITOR_SDK_PORT") or DEFAULT_PORT)
    mode_key = "readonly" if mode == "readonly" else "edit"
    type_params = dict(_URL_PARAMS[doc_type].get(mode_key) or {})
    global_pad_id = hashlib.md5(str(path).encode("utf-8")).hexdigest()
    params: dict[str, str] = {
        "title": path.name,
        "localFilePath": str(path),
        "globalPadId": global_pad_id,
        **type_params,
    }
    if doc_type == "doc":
        params["editorSdkUrl"] = f"http://127.0.0.1:{want_port}"
    qs = urllib.parse.urlencode(params)
    return f"http://127.0.0.1:{want_port}/static/{doc_type}/pc.html?{qs}"


def present_office(
    file_path: str,
    *,
    open_browser: bool = True,
    target: str | None = None,
    mode: str = "edit",
) -> dict[str, Any]:
    """Ensure editor_sdk is up and return (optionally open) the visual URL."""
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        return {"ok": False, "error": f"file not found: {path}"}
    doc_type = sdk_doc_type(path)
    if not doc_type:
        return {"ok": False, "error": f"unsupported format for SDK present: {path.suffix}"}

    status = ensure_sdk()
    if not status.get("ok"):
        return {
            "ok": False,
            "error": status.get("error") or "editor_sdk unavailable",
            "hint": "set EDITOR_SDK_BIN or run plugin/scripts/fetch-sdk.sh",
            **{k: status.get(k) for k in ("bin", "port") if status.get(k)},
        }

    port = status.get("port") or os.environ.get("EDITOR_SDK_PORT") or DEFAULT_PORT
    try:
        url = build_sdk_preview_url(path, port=port, mode=mode)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    opened = False
    opened_where = "none"
    want = (target or os.environ.get("DOCUMENT_PREVIEW_TARGET") or "cursor").lower()
    if open_browser and os.environ.get("DOCUMENT_PREVIEW_NO_OPEN") != "1":
        # Prefer Cursor Simple Browser (same helper as md present)
        if want in ("cursor", "ide", "simple-browser", "auto"):
            try:
                from preview_server import _open_in_cursor_simple_browser

                if _open_in_cursor_simple_browser(url):
                    opened = True
                    opened_where = "cursor-simple-browser"
            except Exception:
                pass
        if not opened and want in ("browser", "system", "auto", "cursor", "ide", "simple-browser"):
            try:
                import subprocess

                subprocess.Popen(
                    ["open", url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                opened = True
                opened_where = "system-browser"
            except OSError:
                pass

    return {
        "ok": True,
        "format": {"doc": "docx", "sheet": "xlsx", "slide": "pptx", "pdf": "pdf"}[doc_type],
        "sdk_type": doc_type,
        "file_path": str(path),
        "url": url,
        "port": int(port) if str(port).isdigit() else port,
        "engine": "editor_sdk",
        "opened_browser": opened,
        "opened_where": opened_where,
        "note": "Visual Office editor via editor_sdk /static/*/pc.html (not headless open_file alone).",
    }
