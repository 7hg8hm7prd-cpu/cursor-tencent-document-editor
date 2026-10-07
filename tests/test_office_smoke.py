#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Optional office smoke tests — skip if editor_sdk is down."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server"))

from bridge import document_convert, document_edit, document_preview, sdk_status  # noqa: E402
from sdk_client import is_alive  # noqa: E402


@unittest.skipUnless(is_alive() or sdk_status().get("ok"), "editor_sdk not available")
class OfficeSmokeTests(unittest.TestCase):
    def test_md_to_docx_roundtrip_preview(self):
        with tempfile.TemporaryDirectory() as td:
            md = Path(td) / "a.md"
            docx = Path(td) / "a.docx"
            md.write_text("# T\n\nbody\n", encoding="utf-8")
            conv = document_convert(str(md), "docx", str(docx))
            self.assertTrue(conv.get("ok"), conv)
            self.assertTrue(docx.is_file())
            prev = document_preview(str(docx))
            self.assertTrue(prev.get("ok"), prev)
            self.assertIn("T", prev.get("content", ""))

    def test_xlsx_edit_preview(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "b.xlsx"
            edited = document_edit(str(path), "A,B\n1,2\n", format="xlsx")
            self.assertTrue(edited.get("ok"), edited)
            prev = document_preview(str(path))
            self.assertTrue(prev.get("ok"), prev)
            self.assertIn("1,2", prev.get("content", ""))

    def test_pptx_edit_preview(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "c.pptx"
            edited = document_edit(str(path), "# One\nAAA\n\n# Two\nBBB\n", format="pptx")
            self.assertTrue(edited.get("ok"), edited)
            prev = document_preview(str(path))
            self.assertTrue(prev.get("ok"), prev)
            self.assertGreaterEqual(prev.get("slide_count") or 0, 1)


if __name__ == "__main__":
    unittest.main()
