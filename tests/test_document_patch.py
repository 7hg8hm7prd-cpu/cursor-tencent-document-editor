#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for document_patch (mock editor_sdk tool_call)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server"))

import bridge  # noqa: E402


def test_document_patch_docx_find_replace(tmp_path):
    docx = tmp_path / "a.docx"
    docx.write_bytes(b"PK\x03\x04fake")

    calls = []

    def fake_tool(name, args, timeout=60):
        calls.append((name, args))
        if name == "open_file":
            return {"file_id": "fid-1"}
        if name in ("doc_find_and_replace", "doc_replace_text"):
            return {"ok": True, "count": 1}
        if name == "save_file":
            return {"ok": True}
        return {"ok": True}

    with patch.object(bridge, "ensure_sdk", return_value={"ok": True}):
        with patch.object(bridge, "tool_call", side_effect=fake_tool):
            out = bridge.document_patch(
                str(docx),
                ops=[{"op": "find_replace", "find": "旧", "replace": "新"}],
            )
    assert out["ok"] is True
    assert out["file_id"] == "fid-1"
    names = [c[0] for c in calls]
    assert "open_file" in names
    assert "save_file" in names
    assert "doc_find_and_replace" in names or "doc_replace_text" in names
    assert bridge._cached_file_id(docx.resolve()) == "fid-1"


def test_document_edit_in_place_redirects():
    out = bridge.document_edit(
        "/tmp/nope.docx",
        content="x",
        format="docx",
        mode="in_place",
    )
    assert out["ok"] is False
    assert out.get("hint") == "document_patch"


def test_document_patch_rejects_md(tmp_path):
    p = tmp_path / "n.md"
    p.write_text("# hi\n", encoding="utf-8")
    out = bridge.document_patch(str(p), ops=[{"op": "find_replace", "find": "a", "replace": "b"}])
    assert out["ok"] is False
