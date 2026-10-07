#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for md/html bridge paths (no editor_sdk required)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server"))

from bridge import _html_to_md, _md_to_html, document_convert, document_edit, document_preview  # noqa: E402


class MdHtmlBridgeTests(unittest.TestCase):
    def test_md_preview_and_edit(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "note.md"
            path.write_text("# Hello\n\nworld\n", encoding="utf-8")
            prev = document_preview(str(path))
            self.assertTrue(prev.get("ok"))
            self.assertEqual(prev.get("format"), "md")
            self.assertIn("Hello", prev.get("content", ""))

            edited = document_edit(str(path), "# Updated\n\nbody\n", format="md")
            self.assertTrue(edited.get("ok"))
            self.assertIn("Updated", path.read_text(encoding="utf-8"))

    def test_md_to_html_convert(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "a.md"
            dst = Path(td) / "a.html"
            src.write_text("# Title\n\n- item\n", encoding="utf-8")
            result = document_convert(str(src), "html", str(dst))
            self.assertTrue(result.get("ok"), result)
            html = dst.read_text(encoding="utf-8")
            self.assertIn("<h1>", html)
            self.assertIn("<li>", html)

    def test_html_to_md_helpers(self):
        html = "<h1>A</h1><p>b <strong>c</strong></p>"
        md = _html_to_md(html)
        self.assertIn("# A", md)
        self.assertIn("**c**", md)
        back = _md_to_html("# Z\n\nhello")
        self.assertIn("<h1>", back)
        self.assertIn("<p>", back)

    def test_pdf_edit_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.pdf"
            path.write_bytes(b"%PDF-1.4\n")
            result = document_edit(str(path), "nope", format="pdf")
            self.assertFalse(result.get("ok"))


class McpServerProtocolTests(unittest.TestCase):
    def test_tools_list_shape(self):
        from server import TOOLS, handle  # noqa: WPS433

        names = {t["name"] for t in TOOLS}
        self.assertEqual(
            names,
            {
                "document_present",
                "document_preview",
                "document_edit",
                "document_patch",
                "document_ai_rewrite",
                "document_convert",
                "document_sdk_status",
            },
        )
        resp = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(resp["id"], 1)
        self.assertIn("tools", resp["result"])

    def test_initialize(self):
        from server import handle  # noqa: WPS433

        resp = handle(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
            }
        )
        self.assertEqual(resp["result"]["serverInfo"]["name"], "tencent-document-editor")

    def test_preview_tool_call_md(self):
        from server import call_tool  # noqa: WPS433

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.md"
            path.write_text("hi\n", encoding="utf-8")
            out = call_tool("document_preview", {"file_path": str(path)})
            payload = json.loads(out["content"][0]["text"])
            self.assertTrue(payload.get("ok"))


if __name__ == "__main__":
    unittest.main()
