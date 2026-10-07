#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Office AI rewrite: Hermes inline-edit → editor_sdk write-back.

WorkBuddy-aligned path:
  mqq selection (text + ranges + fileId) → model → doc_replace_text / find_replace → save.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bridge import _abs, _ensure_office_file_id, detect_format, document_patch
from hermes_ai import ai_status, inline_edit
from sdk_client import SdkError


def _norm_ranges(ranges: list | None) -> list[dict[str, int]]:
    out: list[dict[str, int]] = []
    if not isinstance(ranges, list):
        return out
    for r in ranges:
        if not isinstance(r, dict):
            continue
        try:
            begin = int(r.get("begin"))
            end = int(r.get("end"))
        except (TypeError, ValueError):
            continue
        if begin <= end:
            out.append({"begin": begin, "end": end})
    return out


def _selection_text_from_payload(selection: str, ranges: list[dict[str, int]] | None) -> str:
    return (selection or "").strip()


def office_ai_rewrite(
    file_path: str,
    selection: str,
    instruction: str,
    *,
    apply: bool = True,
    model: str | None = None,
    format: str | None = None,
    replacement: str | None = None,
    ranges: list | None = None,
    file_id: str | None = None,
) -> dict[str, Any]:
    path = _abs(file_path)
    if not path.is_file():
        return {"ok": False, "error": f"file not found: {path}"}
    fmt = detect_format(path, format)
    if fmt not in ("docx", "xlsx", "pptx"):
        return {
            "ok": False,
            "error": f"office AI apply supports docx/xlsx/pptx only, got {fmt}",
            "format": fmt,
            "hint": "md/html use document_ai_rewrite without apply, or Present AI bar",
        }
    sel = _selection_text_from_payload(selection, None)
    inst = (instruction or "").strip()
    range_list = _norm_ranges(ranges)
    if not sel and not range_list:
        return {
            "ok": False,
            "error": "selection is required — 在编辑器中划选，或粘贴选中原文",
        }

    # Apply path may reuse a previewed replacement (skip second Hermes call).
    reuse = (replacement or "").strip() if replacement is not None else ""
    if reuse:
        new_text = reuse
    else:
        if not inst:
            return {"ok": False, "error": "instruction is required"}
        if not sel:
            return {
                "ok": False,
                "error": "选区无文本（可能是图片/对象）。请改选文字后再试。",
            }
        status = ai_status()
        if not status.get("ok"):
            return status
        edited = inline_edit(sel, inst, model=model)
        if edited.get("ok") is False:
            return edited
        new_text = str(edited.get("replacement") or edited.get("text") or "")
        if not new_text.strip():
            return {"ok": False, "error": "empty replacement from Hermes"}

    out: dict[str, Any] = {
        "ok": True,
        "format": fmt,
        "file_path": str(path),
        "selection": sel,
        "instruction": inst,
        "replacement": new_text,
        "applied": False,
        "engine": "hermes+editor_sdk",
        "write_mode": None,
    }
    if range_list:
        out["ranges"] = range_list
    if not apply:
        return out

    try:
        ensured = file_id or _ensure_office_file_id(path, fmt)
        # Prefer precise range replace (WorkBuddy / doc_replace_text) for Word.
        if fmt == "docx" and range_list:
            patch = document_patch(
                str(path),
                ops=[
                    {
                        "op": "replace_range",
                        "ranges": range_list,
                        "text": str(new_text),
                    }
                ],
                format=fmt,
            )
            out["write_mode"] = "replace_range"
        elif sel:
            scope = None
            if fmt == "docx" and range_list and len(range_list) == 1:
                scope = {
                    "type": "range",
                    "begin": range_list[0]["begin"],
                    "end": range_list[0]["end"],
                }
            op: dict[str, Any] = {
                "op": "find_replace",
                "find": sel,
                "replace": str(new_text),
                "replace_all": False,
            }
            if scope:
                op["scope"] = scope
            patch = document_patch(str(path), ops=[op], format=fmt)
            out["write_mode"] = "find_replace_scoped" if scope else "find_replace"
        else:
            return {
                "ok": False,
                "error": "无法写回：缺少选区文本，且无可用 ranges",
                "replacement": new_text,
                "file_path": str(path),
                "format": fmt,
            }

        if not patch.get("ok"):
            return {
                "ok": False,
                "error": patch.get("error") or "document_patch failed",
                "replacement": new_text,
                "file_path": str(path),
                "format": fmt,
                "write_mode": out.get("write_mode"),
            }
        out["applied"] = True
        out["file_id"] = patch.get("file_id") or ensured
        out["patch"] = {"applied": patch.get("applied")}
        return out
    except SdkError as e:
        return {
            "ok": False,
            "error": str(e),
            "replacement": new_text,
            "file_path": str(path),
            "format": fmt,
        }
