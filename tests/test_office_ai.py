#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for Office AI rewrite (Hermes + document_patch)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server"))

import hermes_ai  # noqa: E402
import office_ai  # noqa: E402


def test_office_ai_preview_calls_hermes(tmp_path):
    doc = tmp_path / "a.docx"
    doc.write_bytes(b"PK\x03\x04fake")
    with patch.object(office_ai, "ai_status", return_value={"ok": True}):
        with patch.object(
            office_ai,
            "inline_edit",
            return_value={"ok": True, "replacement": "新句"},
        ) as ie:
            with patch.object(office_ai, "document_patch") as patch_fn:
                out = office_ai.office_ai_rewrite(
                    str(doc), "旧句", "改短一点", apply=False
                )
    assert out["ok"] is True
    assert out["replacement"] == "新句"
    assert out["applied"] is False
    ie.assert_called_once()
    patch_fn.assert_not_called()


def test_office_ai_apply_reuses_replacement(tmp_path):
    doc = tmp_path / "b.docx"
    doc.write_bytes(b"PK\x03\x04fake")
    with patch.object(office_ai, "ai_status") as st:
        with patch.object(office_ai, "inline_edit") as ie:
            with patch.object(
                office_ai,
                "_ensure_office_file_id",
                return_value="fid-1",
            ):
                with patch.object(
                    office_ai,
                    "document_patch",
                    return_value={"ok": True, "file_id": "fid-1", "applied": 1},
                ) as patch_fn:
                    out = office_ai.office_ai_rewrite(
                        str(doc),
                        "旧句",
                        "",
                        apply=True,
                        replacement="预览结果",
                    )
    assert out["ok"] is True
    assert out["applied"] is True
    assert out["replacement"] == "预览结果"
    st.assert_not_called()
    ie.assert_not_called()
    assert patch_fn.called
    call_ops = patch_fn.call_args.kwargs.get("ops")
    if call_ops is None and patch_fn.call_args.args:
        # positional: document_patch(path, ops=...) or (path, ops)
        if len(patch_fn.call_args.args) > 1:
            call_ops = patch_fn.call_args.args[1]
    assert call_ops[0]["find"] == "旧句"
    assert call_ops[0]["replace"] == "预览结果"


def test_office_ai_rejects_non_office(tmp_path):
    p = tmp_path / "n.md"
    p.write_text("# hi\n", encoding="utf-8")
    out = office_ai.office_ai_rewrite(str(p), "a", "b", apply=False)
    assert out["ok"] is False


def test_document_ai_rewrite_routes_office(tmp_path):
    doc = tmp_path / "c.docx"
    doc.write_bytes(b"PK\x03\x04fake")
    with patch("office_ai.office_ai_rewrite") as oa:
        oa.return_value = {"ok": True, "applied": True, "replacement": "Z"}
        out = hermes_ai.document_ai_rewrite(
            "指令",
            selection="sel",
            file_path=str(doc),
            apply=True,
        )
    assert out["ok"] is True
    oa.assert_called_once()
    assert oa.call_args.kwargs.get("apply") is True


def test_office_ai_apply_uses_replace_range(tmp_path):
    doc = tmp_path / "d.docx"
    doc.write_bytes(b"PK\x03\x04fake")
    with patch.object(office_ai, "_ensure_office_file_id", return_value="fid"):
        with patch.object(
            office_ai,
            "document_patch",
            return_value={"ok": True, "file_id": "fid", "applied": 1},
        ) as patch_fn:
            out = office_ai.office_ai_rewrite(
                str(doc),
                "旧",
                "",
                apply=True,
                replacement="新",
                ranges=[{"begin": 10, "end": 12, "length": 2}],
            )
    assert out["ok"] is True
    assert out["applied"] is True
    assert out["write_mode"] == "replace_range"
    ops = patch_fn.call_args.kwargs.get("ops") or patch_fn.call_args.args[1]
    assert ops[0]["op"] == "replace_range"
    assert ops[0]["ranges"][0]["begin"] == 10
