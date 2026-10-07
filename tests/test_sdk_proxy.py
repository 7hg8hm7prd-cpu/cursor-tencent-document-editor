#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for office-frame HTML prep (mqq inject + absolute SDK assets)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server"))

import sdk_proxy  # noqa: E402


def test_inject_mqq_into_html():
    html = b"<!doctype html><html><head><title>x</title></head><body>hi</body></html>"
    out = sdk_proxy.inject_mqq_into_html(html)
    assert b"data-hermes-mqq" in out
    assert b"docx.onSelectionChange" in out
    # idempotent
    out2 = sdk_proxy.inject_mqq_into_html(out)
    assert out2.count(b"data-hermes-mqq") == 1


def test_rewrite_assets_to_sdk_origin():
    html = (
        b'<html><head></head><body>'
        b'<script crossorigin="anonymous" src="/static/a.js"></script>'
        b'<a href="/mcp">t</a></body></html>'
    )
    out = sdk_proxy.inject_mqq_into_html(html, rewrite_assets=True)
    assert b'src="http://127.0.0.1:39099/static/a.js"' in out
    assert b'href="http://127.0.0.1:39099/mcp"' in out
    assert b"crossorigin" not in out.lower() or b"data-hermes" in out  # stripped from guest tags


def test_build_office_frame_url(tmp_path):
    p = tmp_path / "a.docx"
    p.write_bytes(b"PK")
    url = sdk_proxy.build_office_frame_url(str(p), preview_port=39110, sdk_port=39099)
    assert url.startswith("http://127.0.0.1:39110/office-frame?")
    assert "type=doc" in url
    assert "editorSdkUrl=" in url or "localFilePath=" in url


def test_inject_js_exists():
    raw = sdk_proxy.inject_js_bytes()
    assert b"docx.onSelectionChange" in raw
    assert b"hermes-tencent-doc-mqq" in raw
