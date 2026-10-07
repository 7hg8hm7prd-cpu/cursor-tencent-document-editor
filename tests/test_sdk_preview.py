#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server"))

from sdk_preview import build_sdk_preview_url, present_office, sdk_doc_type  # noqa: E402


def test_sdk_doc_type():
    assert sdk_doc_type("/a/b.docx") == "doc"
    assert sdk_doc_type("/a/b.xlsx") == "sheet"
    assert sdk_doc_type("/a/b.pptx") == "slide"
    assert sdk_doc_type("/a/b.pdf") == "pdf"
    assert sdk_doc_type("/a/b.md") is None


def test_build_sdk_preview_url_docx(tmp_path):
    p = tmp_path / "note.docx"
    p.write_bytes(b"PK")
    url = build_sdk_preview_url(p, port=39099)
    assert url.startswith("http://127.0.0.1:39099/static/doc/pc.html?")
    assert "localFilePath=" in url
    assert "local_edit=1" in url
    assert "editorSdkUrl=" in url
    assert "_wbchat" not in url
    assert "wb_source=local" in url
    pad = hashlib.md5(str(p.resolve()).encode("utf-8")).hexdigest()
    assert f"globalPadId={pad}" in url


def test_present_office_requires_sdk(tmp_path):
    p = tmp_path / "a.docx"
    p.write_bytes(b"PK")
    with patch("sdk_preview.ensure_sdk", return_value={"ok": False, "error": "no bin"}):
        out = present_office(str(p), open_browser=False)
    assert out["ok"] is False
    assert "editor_sdk" in out["error"] or "no bin" in out["error"]


def test_present_office_ok(tmp_path):
    p = tmp_path / "a.xlsx"
    p.write_bytes(b"PK")
    with patch("sdk_preview.ensure_sdk", return_value={"ok": True, "port": "39099"}):
        out = present_office(str(p), open_browser=False)
    assert out["ok"] is True
    assert out["engine"] == "editor_sdk"
    assert "/static/sheet/pc.html" in out["url"]
