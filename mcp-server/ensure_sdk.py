#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Locate and start local editor_sdk if it is not already listening."""

from __future__ import annotations

import os
import platform
import subprocess
import time
from pathlib import Path

from sdk_client import DEFAULT_PORT, is_alive, reset_endpoint

PLUGIN_ROOT = Path(
    os.environ.get("DOCUMENT_EDITOR_PLUGIN_ROOT")
    or Path(__file__).resolve().parents[1]
).resolve()


def _platform_bin_name() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin" and machine in ("arm64", "aarch64"):
        return "darwin-arm64/editor_sdk"
    if system == "darwin":
        return "darwin-x64/editor_sdk"
    if system == "linux" and machine in ("arm64", "aarch64"):
        return "linux-arm64/editor_sdk"
    if system == "linux":
        return "linux-x64/editor_sdk"
    if system == "windows":
        return "win-x64/editor_sdk.exe"
    return "darwin-arm64/editor_sdk"


def resolve_sdk_bin() -> Path | None:
    env = os.environ.get("EDITOR_SDK_BIN", "").strip()
    if env:
        p = Path(env).expanduser()
        if p.is_file():
            return p.resolve()

    home = Path.home()
    candidates = [
        PLUGIN_ROOT / ".." / "third_party" / "tencent-editor-sdk" / _platform_bin_name(),
        PLUGIN_ROOT.parent / "third_party" / "tencent-editor-sdk" / _platform_bin_name(),
        Path.cwd() / "third_party" / "tencent-editor-sdk" / _platform_bin_name(),
        # tax-hermes checkout (standalone plugin often lives beside or under it)
        home / "tax-hermes" / "third_party" / "tencent-editor-sdk" / _platform_bin_name(),
        Path("/Users/henry/tax-hermes/third_party/tencent-editor-sdk") / _platform_bin_name(),
    ]
    for c in candidates:
        try:
            if c.is_file():
                return c.resolve()
        except OSError:
            continue
    return None


def ensure_sdk(wait_s: float = 8.0) -> dict:
    """Ensure editor_sdk is reachable. Start it if needed."""
    if is_alive():
        return {"ok": True, "started": False, "port": os.environ.get("EDITOR_SDK_PORT", str(DEFAULT_PORT))}

    bin_path = resolve_sdk_bin()
    if not bin_path:
        return {
            "ok": False,
            "started": False,
            "error": "editor_sdk binary not found; set EDITOR_SDK_BIN",
        }

    port = str(os.environ.get("EDITOR_SDK_PORT", DEFAULT_PORT))
    log_dir = Path(os.environ.get("EDITOR_SDK_LOG_DIR") or "/tmp/editor_sdk_logs")
    tmp_dir = Path(os.environ.get("EDITOR_SDK_TMP_DIR") or "/tmp/editor_sdk_tmp")
    log_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # Allow Cursor/Simple Browser iframes to load editor assets from 127.0.0.1
    cors = (os.environ.get("EDITOR_SDK_CORS_ORIGIN") or "*").strip() or "*"
    # WorkBuddy default: do NOT pass -td_proxy (that is the online/docs.qq.com path).
    # Local open uses client=sdk_local + local_edit=1 + localFilePath only.
    enable_td = (os.environ.get("EDITOR_SDK_TD_PROXY") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    out_log = log_dir / "editor_sdk.stdout.log"
    try:
        with open(out_log, "ab") as logf:
            args = [
                str(bin_path),
                f"--port={port}",
                f"--log_dir={log_dir}",
                f"--tmp_dir={tmp_dir}",
                f"--cors_origin={cors}",
            ]
            if enable_td:
                args.append("-td_proxy=true")
            subprocess.Popen(
                args,
                stdout=logf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except OSError as e:
        return {"ok": False, "started": False, "error": f"spawn failed: {e}", "bin": str(bin_path)}

    deadline = time.time() + wait_s
    while time.time() < deadline:
        time.sleep(0.4)
        reset_endpoint()
        if is_alive():
            return {"ok": True, "started": True, "port": port, "bin": str(bin_path)}

    return {
        "ok": False,
        "started": True,
        "error": f"editor_sdk started but not ready within {wait_s}s; see {out_log}",
        "bin": str(bin_path),
        "port": port,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(ensure_sdk(), ensure_ascii=False, indent=2))
