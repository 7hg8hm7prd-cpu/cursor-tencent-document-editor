#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stdio MCP server for Cursor: document_preview / document_edit / document_convert.

Transport: MCP stdio with Content-Length framing (also accepts NDJSON lines).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterator

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from bridge import (  # noqa: E402
    document_convert,
    document_edit,
    document_patch,
    document_present,
    document_preview,
    sdk_status,
)
from hermes_ai import document_ai_rewrite  # noqa: E402

SERVER_NAME = "tencent-document-editor"
SERVER_VERSION = "1.5.0"

TOOLS = [
    {
        "name": "document_present",
        "description": (
            "WorkBuddy-style present: open a local WYSIWYG editor for .md / .html "
            "in the browser (visual edit + save back to disk). "
            "Prefer this as the DEFAULT when the user wants to view/edit Markdown or HTML. "
            "Office files (docx/pptx/xlsx) should use document_preview + editor_sdk instead."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to .md or .html file",
                },
                "open_browser": {
                    "type": "boolean",
                    "description": "Open a viewer automatically (default true)",
                },
                "target": {
                    "type": "string",
                    "enum": ["cursor", "browser", "auto"],
                    "description": "Where to open: cursor=IDE Simple Browser (default), browser=system browser, auto=try cursor then browser",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "document_preview",
        "description": (
            "Preview a local document (md/html/docx/pptx/xlsx/pdf). "
            "Returns readable text content and metadata. PDF is view-only. "
            "For interactive md/html editing prefer document_present."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute or workspace-relative file path",
                },
                "format": {
                    "type": "string",
                    "enum": ["md", "html", "docx", "pptx", "xlsx", "pdf"],
                    "description": "Optional format override; default from extension",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "document_edit",
        "description": (
            "Write/replace document content. "
            "md/html: overwrite text file. "
            "docx/pptx/xlsx with mode=rewrite (default): create_* rebuild via editor_sdk. "
            "For in-place Office edits use document_patch. "
            "pdf: not supported."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Destination file path"},
                "content": {"type": "string", "description": "Full document content to write"},
                "format": {
                    "type": "string",
                    "enum": ["md", "html", "docx", "pptx", "xlsx", "pdf"],
                    "description": "Target format; default from extension",
                },
                "content_format": {
                    "type": "string",
                    "enum": ["md", "html", "text", "csv"],
                    "description": "How to interpret content when writing office files (default md)",
                },
                "mode": {
                    "type": "string",
                    "enum": ["rewrite", "in_place"],
                    "description": "rewrite=full rebuild (default). in_place redirects to document_patch.",
                },
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "document_patch",
        "description": (
            "In-place Office edit: open existing docx/xlsx/pptx, apply ops, save. "
            "docx: find_replace; xlsx: set_csv / replace; pptx: find_replace. "
            "Prefer this over document_edit for small changes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Existing Office file path"},
                "format": {
                    "type": "string",
                    "enum": ["docx", "pptx", "xlsx"],
                    "description": "Optional format override",
                },
                "ops": {
                    "type": "array",
                    "description": "List of patch operations",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {
                                "type": "string",
                                "enum": ["find_replace", "replace", "set_csv", "set_range"],
                            },
                            "find": {"type": "string"},
                            "replace": {"type": "string"},
                            "csv_data": {"type": "string"},
                            "sheet_id": {"type": "string"},
                            "start_row": {"type": "integer"},
                            "start_col": {"type": "integer"},
                            "page_index": {"type": "integer"},
                            "replace_all": {"type": "boolean"},
                        },
                        "required": ["op"],
                    },
                },
            },
            "required": ["file_path", "ops"],
        },
    },
    {
        "name": "document_ai_rewrite",
        "description": (
            "AI rewrite via local Hermes WebUI (HERMES_WEBUI_BASE). "
            "Provide selection (inline-edit) or parts (canvas rewrite). "
            "Requires Hermes running on this machine."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "instruction": {"type": "string", "description": "How to rewrite"},
                "selection": {"type": "string", "description": "Selected text for inline-edit"},
                "parts": {
                    "type": "array",
                    "description": "Block parts [{id, md|html}]",
                    "items": {"type": "object"},
                },
                "format": {
                    "type": "string",
                    "enum": ["md", "html"],
                    "description": "Content format for parts rewrite (default md)",
                },
                "model": {"type": "string"},
                "file_path": {
                    "type": "string",
                    "description": "Optional path for logging / validation only",
                },
            },
            "required": ["instruction"],
        },
    },
    {
        "name": "document_convert",
        "description": (
            "Convert between formats: md↔html, md/html→docx/pptx/xlsx, "
            "office/pdf→md/html (text extract), xlsx→csv."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Source file path"},
                "to_format": {
                    "type": "string",
                    "enum": ["md", "html", "docx", "pptx", "xlsx", "pdf", "csv"],
                    "description": "Target format",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional destination path; default: same stem with new extension",
                },
                "from_format": {
                    "type": "string",
                    "enum": ["md", "html", "docx", "pptx", "xlsx", "pdf"],
                    "description": "Optional source format override",
                },
            },
            "required": ["file_path", "to_format"],
        },
    },
    {
        "name": "document_sdk_status",
        "description": "Check or start local editor_sdk; returns port and health.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _ok_text(payload: Any) -> dict:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}]}


def _err_text(message: str) -> dict:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"ok": False, "error": message}, ensure_ascii=False),
            }
        ],
        "isError": True,
    }


def call_tool(name: str, arguments: dict | None) -> dict:
    args = arguments or {}
    try:
        if name == "document_present":
            open_browser = args.get("open_browser")
            if open_browser is None:
                open_browser = True
            return _ok_text(
                document_present(
                    args.get("file_path", ""),
                    bool(open_browser),
                    args.get("target"),
                )
            )
        if name == "document_preview":
            return _ok_text(document_preview(args.get("file_path", ""), args.get("format")))
        if name == "document_edit":
            return _ok_text(
                document_edit(
                    args.get("file_path", ""),
                    args.get("content", ""),
                    args.get("format"),
                    args.get("content_format"),
                    args.get("mode"),
                )
            )
        if name == "document_patch":
            return _ok_text(
                document_patch(
                    args.get("file_path", ""),
                    args.get("ops"),
                    args.get("format"),
                )
            )
        if name == "document_ai_rewrite":
            return _ok_text(
                document_ai_rewrite(
                    args.get("instruction", ""),
                    selection=args.get("selection"),
                    parts=args.get("parts"),
                    format=str(args.get("format") or "md"),
                    model=args.get("model"),
                    file_path=args.get("file_path"),
                )
            )
        if name == "document_convert":
            return _ok_text(
                document_convert(
                    args.get("file_path", ""),
                    args.get("to_format", ""),
                    args.get("output_path"),
                    args.get("from_format"),
                )
            )
        if name == "document_sdk_status":
            return _ok_text(sdk_status())
        return _err_text(f"unknown tool: {name}")
    except Exception as e:  # noqa: BLE001
        return _err_text(str(e))


def handle(msg: dict) -> dict | None:
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        name = params.get("name") or ""
        result = call_tool(name, params.get("arguments") or {})
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    if method == "resources/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"resources": []}}

    if method == "prompts/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"prompts": []}}

    # Notification without id — ignore unknown
    if msg_id is None:
        return None

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def _write_message(obj: dict) -> None:
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def _read_messages() -> Iterator[dict]:
    """Read Content-Length framed messages; fall back to NDJSON lines."""
    buffer = b""
    while True:
        chunk = sys.stdin.buffer.read(1)
        if not chunk:
            if buffer.strip():
                # leftover NDJSON
                try:
                    yield json.loads(buffer.decode("utf-8"))
                except json.JSONDecodeError:
                    pass
            return
        buffer += chunk

        # Content-Length framing
        if b"\r\n\r\n" in buffer or b"\n\n" in buffer:
            sep = b"\r\n\r\n" if b"\r\n\r\n" in buffer else b"\n\n"
            header_blob, rest = buffer.split(sep, 1)
            header_text = header_blob.decode("ascii", errors="replace")
            length = None
            for line in header_text.splitlines():
                if line.lower().startswith("content-length:"):
                    try:
                        length = int(line.split(":", 1)[1].strip())
                    except ValueError:
                        length = None
            if length is None:
                # Treat as NDJSON line(s)
                for line in header_text.splitlines():
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            pass
                buffer = rest
                continue

            while len(rest) < length:
                more = sys.stdin.buffer.read(length - len(rest))
                if not more:
                    return
                rest += more
            body = rest[:length]
            buffer = rest[length:]
            try:
                yield json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            continue

        # NDJSON: complete line without Content-Length header
        if b"\n" in buffer and b"content-length:" not in buffer.lower():
            line, buffer = buffer.split(b"\n", 1)
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                yield json.loads(text)
            except json.JSONDecodeError:
                continue


def main() -> None:
    for msg in _read_messages():
        if isinstance(msg, list):
            for item in msg:
                if isinstance(item, dict):
                    resp = handle(item)
                    if resp is not None:
                        _write_message(resp)
            continue
        if not isinstance(msg, dict):
            continue
        resp = handle(msg)
        if resp is not None:
            _write_message(resp)


if __name__ == "__main__":
    main()
