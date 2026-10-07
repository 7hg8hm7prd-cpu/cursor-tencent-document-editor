#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Boot upstream editor_sdk + public-port inject proxy (WorkBuddy parity).

WorkBuddy: bare editor_sdk + Electron preload (mqq + __WB_DOCS_FEATURE_LIST__).
Cursor: bare editor_sdk on UPSTREAM + Node sdk_inject_proxy.js on PUBLIC
        (injects same main-world surface; tunnels WebSocket).

Set HERMES_SDK_DIRECT=1 to skip inject and bind bare editor_sdk on PUBLIC.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC = int(os.environ.get("EDITOR_SDK_PORT") or "39099")
UPSTREAM = int(os.environ.get("EDITOR_SDK_UPSTREAM_PORT") or "39101")
PLUGIN_ROOT = Path(
    os.environ.get("DOCUMENT_EDITOR_PLUGIN_ROOT") or ROOT.parent
).resolve()
DIRECT = (os.environ.get("HERMES_SDK_DIRECT") or "").strip().lower() in (
    "1",
    "true",
    "yes",
)


def busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.25)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except OSError:
            return False


def has_inject(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/static/doc/pc.html", timeout=3
        ) as resp:
            body = resp.read(24000)
            return b"data-hermes-mqq" in body or b"__WB_DOCS_FEATURE_LIST__" in body
    except Exception:
        return False


def kill_port(port: int) -> None:
    subprocess.run(
        f"lsof -ti :{port} | xargs kill -9 2>/dev/null",
        shell=True,
        check=False,
    )
    time.sleep(0.4)


def start_bare_sdk(port: int) -> bool:
    env = os.environ.copy()
    env["EDITOR_SDK_PORT"] = str(port)
    env["DOCUMENT_EDITOR_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    env["EDITOR_SDK_CORS_ORIGIN"] = env.get("EDITOR_SDK_CORS_ORIGIN") or "*"
    env.pop("EDITOR_SDK_TD_PROXY", None)
    if busy(port):
        kill_port(port)
    subprocess.run(
        [sys.executable, str(ROOT / "ensure_sdk.py")],
        env=env,
        timeout=60,
        check=False,
    )
    for _ in range(40):
        time.sleep(0.25)
        if busy(port):
            return True
    return False


def resolve_node() -> str:
    for cand in ("node", "/usr/local/bin/node", "/opt/homebrew/bin/node"):
        if cand == "node":
            found = shutil.which("node")
            if found:
                return found
        elif Path(cand).is_file():
            return cand
    return "node"


def start_inject_proxy() -> bool:
    log_dir = Path(os.environ.get("EDITOR_SDK_LOG_DIR") or "/tmp/editor_sdk_logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    env2 = os.environ.copy()
    env2["EDITOR_SDK_PORT"] = str(PUBLIC)
    env2["EDITOR_SDK_UPSTREAM_PORT"] = str(UPSTREAM)
    env2["DOCUMENT_EDITOR_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    proxy_js = ROOT / "sdk_inject_proxy.js"
    if not proxy_js.is_file():
        return False
    with open(log_dir / "sdk_inject_proxy.log", "ab") as logf:
        subprocess.Popen(
            [resolve_node(), str(proxy_js)],
            env=env2,
            stdout=logf,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    for _ in range(50):
        time.sleep(0.2)
        if busy(PUBLIC) and has_inject(PUBLIC):
            return True
    return False


def main() -> int:
    if DIRECT:
        if busy(PUBLIC) and not has_inject(PUBLIC):
            print(json.dumps({"ok": True, "mode": "direct", "port": PUBLIC}))
            return 0
        kill_port(PUBLIC)
        kill_port(UPSTREAM)
        ok = start_bare_sdk(PUBLIC)
        print(json.dumps({"ok": ok, "mode": "direct", "port": PUBLIC}))
        return 0 if ok else 1

    if busy(PUBLIC) and has_inject(PUBLIC):
        print(
            json.dumps(
                {"ok": True, "started": False, "port": PUBLIC, "inject": True, "ws": True}
            )
        )
        return 0

    if busy(PUBLIC):
        kill_port(PUBLIC)

    if not busy(UPSTREAM):
        if not start_bare_sdk(UPSTREAM):
            ok = start_bare_sdk(PUBLIC)
            print(
                json.dumps(
                    {
                        "ok": ok,
                        "mode": "direct-fallback",
                        "port": PUBLIC,
                        "error": f"upstream :{UPSTREAM} failed",
                    }
                )
            )
            return 0 if ok else 1

    if start_inject_proxy():
        print(
            json.dumps(
                {
                    "ok": True,
                    "started": True,
                    "port": PUBLIC,
                    "upstream": UPSTREAM,
                    "inject": True,
                    "ws": True,
                    "proxy": "node",
                }
            )
        )
        return 0

    kill_port(PUBLIC)
    ok = start_bare_sdk(PUBLIC)
    print(
        json.dumps(
            {
                "ok": ok,
                "mode": "direct-fallback",
                "port": PUBLIC,
                "error": "inject proxy not ready",
            }
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
