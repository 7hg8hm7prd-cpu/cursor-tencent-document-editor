#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for Hermes AI proxy (mock HTTP)."""

from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server"))

import hermes_ai  # noqa: E402


class _FakeResp:
    def __init__(self, payload: dict, code: int = 200):
        self._raw = json.dumps(payload).encode("utf-8")
        self.status = code

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_ai_status_ok():
    with patch.object(hermes_ai.urllib.request, "urlopen", return_value=_FakeResp({"status": "ok"})):
        st = hermes_ai.ai_status()
    assert st["ok"] is True
    assert "hermes_base" in st


def test_ai_status_unreachable():
    with patch.object(
        hermes_ai.urllib.request,
        "urlopen",
        side_effect=urllib.error.URLError("conn refused"),
    ):
        st = hermes_ai.ai_status()
    assert st["ok"] is False
    assert "unreachable" in st["error"].lower() or "Hermes" in st["error"]


def test_inline_edit_forwards():
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResp({"ok": True, "replacement": "新文本"})

    with patch.object(hermes_ai.urllib.request, "urlopen", side_effect=fake_urlopen):
        out = hermes_ai.inline_edit("旧", "改短一点")
    assert out["ok"] is True
    assert out["replacement"] == "新文本"
    assert captured["url"].endswith("/api/md/inline-edit")
    assert captured["body"]["selection"] == "旧"


def test_rewrite_forwards():
    def fake_urlopen(req, timeout=None):
        return _FakeResp({"ok": True, "parts": [{"id": "blk-0", "md": "hi"}]})

    with patch.object(hermes_ai.urllib.request, "urlopen", side_effect=fake_urlopen):
        out = hermes_ai.rewrite("润色", [{"id": "blk-0", "md": "hello"}], format="md")
    assert out["ok"] is True
    assert out["parts"][0]["md"] == "hi"


def test_document_ai_rewrite_requires_hermes():
    with patch.object(hermes_ai, "ai_status", return_value={"ok": False, "error": "down"}):
        out = hermes_ai.document_ai_rewrite("x", selection="y")
    assert out["ok"] is False


def test_document_ai_rewrite_selection_path():
    with patch.object(hermes_ai, "ai_status", return_value={"ok": True}):
        with patch.object(
            hermes_ai,
            "inline_edit",
            return_value={"ok": True, "replacement": "Z"},
        ) as ie:
            out = hermes_ai.document_ai_rewrite("指令", selection="sel", file_path="/tmp/a.md")
    assert out["ok"] is True
    assert out["replacement"] == "Z"
    assert out["file_path"] == "/tmp/a.md"
    ie.assert_called_once()
