#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified document preview / edit / convert bridge.

Formats:
  md, html          — direct filesystem read/write (+ light convert)
  docx, pptx, xlsx  — via local editor_sdk MCP tools
  pdf               — preview-only text extract (no editor_sdk edit)
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ensure_sdk import ensure_sdk
from sdk_client import SdkError, tool_call

MAX_PREVIEW_CHARS = 120_000

EXT_FORMAT = {
    ".md": "md",
    ".markdown": "md",
    ".html": "html",
    ".htm": "html",
    ".docx": "docx",
    ".doc": "docx",
    ".wps": "docx",
    ".pptx": "pptx",
    ".ppt": "pptx",
    ".xlsx": "xlsx",
    ".xls": "xlsx",
    ".csv": "xlsx",
    ".pdf": "pdf",
}

OFFICE_FILE_TYPE = {
    "docx": "doc",
    "pptx": "slide",
    "xlsx": "sheet",
}


def _abs(path: str | Path) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    else:
        p = p.resolve()
    return p


def detect_format(path: Path, explicit: str | None = None) -> str:
    if explicit:
        fmt = explicit.lower().lstrip(".")
        if fmt in ("md", "html", "docx", "pptx", "xlsx", "pdf"):
            return fmt
    return EXT_FORMAT.get(path.suffix.lower(), "md")


def _truncate(text: str, limit: int = MAX_PREVIEW_CHARS) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + "\n…(truncated)…", True


def _md_to_html(md: str) -> str:
    """Markdown → HTML for present / convert (tables, tasks, footnotes…)."""
    from md_codec import md_to_html

    return md_to_html(md)


def _html_to_md(raw_html: str) -> str:
    """HTML → Markdown for present save / convert."""
    from md_codec import html_to_md

    return html_to_md(raw_html)


def _require_sdk() -> dict | None:
    status = ensure_sdk()
    if not status.get("ok"):
        return status
    return None


def _open_office(path: Path, fmt: str) -> dict:
    err = _require_sdk()
    if err:
        raise SdkError(err.get("error") or "editor_sdk unavailable")
    file_type = OFFICE_FILE_TYPE[fmt]
    result = tool_call(
        "open_file",
        {
            "file_path": str(path),
            "file_type": file_type,
            "wait": True,
            "open_with_existing": True,
        },
        timeout=300,
    )
    if isinstance(result, dict) and result.get("file_id"):
        return result
    raise SdkError(f"open_file did not return file_id: {result!r}")


def _ready_created(created: dict, file_type: str) -> dict:
    """create_* returns file_id before the model is always editable; force wait-open."""
    if not isinstance(created, dict) or not created.get("file_id"):
        raise SdkError(f"create failed: {created!r}")
    file_id = created["file_id"]
    file_path = created.get("file_path")
    if file_path:
        opened = tool_call(
            "open_file",
            {
                "file_path": str(file_path),
                "file_type": file_type,
                "wait": True,
                "open_with_existing": True,
            },
            timeout=300,
        )
        if isinstance(opened, dict) and opened.get("file_id"):
            file_id = opened["file_id"]
    return {"file_id": file_id, "file_path": file_path, "file_type": file_type}


def _save_office(file_id: str, dest: Path | None = None) -> Any:
    args: dict[str, Any] = {"file_id": file_id}
    if dest is not None:
        args["file_path"] = str(dest)
    return tool_call("save_file", args, timeout=180)


def _preview_md_html(path: Path, fmt: str) -> dict:
    raw = path.read_text(encoding="utf-8", errors="replace")
    body, truncated = _truncate(raw)
    preview_html = _md_to_html(body) if fmt == "md" else body
    return {
        "ok": True,
        "format": fmt,
        "file_path": str(path),
        "content": body,
        "preview_html": preview_html if fmt == "md" else None,
        "truncated": truncated,
        "char_count": len(raw),
        "editable": True,
    }


def _preview_docx(path: Path) -> dict:
    opened = _open_office(path, "docx")
    file_id = opened["file_id"]
    structure = tool_call(
        "doc_resolve_document_structure",
        {"file_id": file_id, "mode": "full", "limit": 200, "text_preview_length": 200},
        timeout=120,
    )
    outline = tool_call("doc_get_outline", {"file_id": file_id}, timeout=60)
    nodes = []
    if isinstance(structure, dict):
        nodes = structure.get("nodes") or structure.get("blocks") or []
    lines: list[str] = []
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict):
            continue
        ntype = node.get("type") or ""
        preview = node.get("text_preview") or node.get("text") or node.get("title") or ""
        if ntype in ("Heading", "Title", "Subtitle") or node.get("heading_level"):
            level = int(node.get("heading_level") or 1)
            lines.append("#" * max(1, min(level, 6)) + " " + str(preview))
        elif preview:
            lines.append(str(preview))
    content = "\n".join(lines) if lines else json.dumps(structure, ensure_ascii=False, indent=2)
    body, truncated = _truncate(content)
    return {
        "ok": True,
        "format": "docx",
        "file_path": str(path),
        "file_id": file_id,
        "content": body,
        "outline": outline,
        "truncated": truncated,
        "editable": True,
        "engine": "editor_sdk",
    }


def _preview_xlsx(path: Path) -> dict:
    opened = _open_office(path, "xlsx")
    file_id = opened["file_id"]
    info = tool_call("sheet_get_sheet_info", {"file_id": file_id}, timeout=60)
    sheets = []
    if isinstance(info, dict):
        sheets = info.get("sheets") or info.get("sheet_list") or info.get("data") or []
    if isinstance(info, list):
        sheets = info

    previews: list[dict] = []
    for sheet in (sheets if isinstance(sheets, list) else [])[:5]:
        if not isinstance(sheet, dict):
            continue
        sheet_id = sheet.get("sheet_id") or sheet.get("id") or sheet.get("SheetId")
        name = sheet.get("name") or sheet.get("sheet_name") or sheet_id
        if not sheet_id:
            continue
        used = tool_call(
            "sheet_get_used_range",
            {"file_id": file_id, "sheet_id": str(sheet_id)},
            timeout=60,
        )
        end_row, end_col = 49, 19
        if isinstance(used, dict) and not used.get("is_empty"):
            ur = used.get("used_range") or used
            if isinstance(ur, dict):
                end_row = min(int(ur.get("end_row") or ur.get("row_end") or 49), 99)
                end_col = min(int(ur.get("end_col") or ur.get("col_end") or 19), 49)
        cells = tool_call(
            "sheet_get_cell_data",
            {
                "file_id": file_id,
                "sheet_id": str(sheet_id),
                "start_row": 0,
                "start_col": 0,
                "end_row": end_row,
                "end_col": end_col,
                "return_csv": True,
            },
            timeout=120,
        )
        csv_data = ""
        if isinstance(cells, dict):
            csv_data = cells.get("csv_data") or cells.get("text") or ""
            if not csv_data and cells.get("raw"):
                csv_data = json.dumps(cells, ensure_ascii=False)
        previews.append({"sheet_id": sheet_id, "name": name, "csv": str(csv_data)[:40_000]})

    content = "\n\n".join(
        f"## {p['name']}\n```csv\n{p['csv']}\n```" for p in previews
    ) or json.dumps(info, ensure_ascii=False, indent=2)
    body, truncated = _truncate(content)
    return {
        "ok": True,
        "format": "xlsx",
        "file_path": str(path),
        "file_id": file_id,
        "sheets": previews,
        "content": body,
        "truncated": truncated,
        "editable": True,
        "engine": "editor_sdk",
    }


def _preview_pptx(path: Path) -> dict:
    opened = _open_office(path, "pptx")
    file_id = opened["file_id"]
    meta = tool_call("slide_get_info", {"file_id": file_id}, timeout=60)
    count = 0
    if isinstance(meta, dict):
        count = int(meta.get("slide_count") or len(meta.get("ordered_slide_ids") or []) or 0)
    pages: list[dict] = []
    for i in range(min(count or 20, 30)):
        try:
            page = tool_call(
                "slide_get_page_info",
                {"file_id": file_id, "page_index": i},
                timeout=60,
            )
        except SdkError:
            break
        texts: list[str] = []
        shapes = []
        if isinstance(page, dict):
            shapes = page.get("shapes") or page.get("shape_list") or []
        for shape in shapes if isinstance(shapes, list) else []:
            if not isinstance(shape, dict):
                continue
            t = shape.get("text") or shape.get("text_content") or ""
            if t:
                texts.append(str(t).strip())
        pages.append({"page_index": i, "texts": texts, "raw": page if not texts else None})

    content_lines = []
    for p in pages:
        content_lines.append(f"### Slide {p['page_index'] + 1}")
        content_lines.extend(p["texts"] or ["(no text)"])
        content_lines.append("")
    content = "\n".join(content_lines) or json.dumps(meta, ensure_ascii=False, indent=2)
    body, truncated = _truncate(content)
    return {
        "ok": True,
        "format": "pptx",
        "file_path": str(path),
        "file_id": file_id,
        "slide_count": count,
        "pages": [{"page_index": p["page_index"], "texts": p["texts"]} for p in pages],
        "content": body,
        "truncated": truncated,
        "editable": True,
        "engine": "editor_sdk",
    }


def _preview_pdf(path: Path) -> dict:
    text = ""
    method = ""
    # 1) pdftotext
    if shutil.which("pdftotext"):
        try:
            proc = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                text = proc.stdout
                method = "pdftotext"
        except (OSError, subprocess.TimeoutExpired):
            pass
    # 2) pypdf
    if not text:
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(path))
            parts = []
            for page in reader.pages[:50]:
                parts.append(page.extract_text() or "")
            text = "\n".join(parts)
            method = "pypdf"
        except Exception:
            pass
    if not text:
        text = (
            f"[PDF preview unavailable] path={path}\n"
            "Install poppler (`pdftotext`) or `pypdf` for text extraction. "
            "PDF is view-only; editor_sdk does not edit PDF."
        )
        method = "none"
    body, truncated = _truncate(text)
    return {
        "ok": True,
        "format": "pdf",
        "file_path": str(path),
        "content": body,
        "truncated": truncated,
        "editable": False,
        "extract_method": method,
    }


def document_preview(file_path: str, format: str | None = None) -> dict:
    path = _abs(file_path)
    if not path.is_file():
        return {"ok": False, "error": f"file not found: {path}"}
    fmt = detect_format(path, format)
    try:
        if fmt in ("md", "html"):
            return _preview_md_html(path, fmt)
        if fmt == "docx":
            return _preview_docx(path)
        if fmt == "xlsx":
            return _preview_xlsx(path)
        if fmt == "pptx":
            return _preview_pptx(path)
        if fmt == "pdf":
            return _preview_pdf(path)
        return {"ok": False, "error": f"unsupported format: {fmt}"}
    except SdkError as e:
        return {"ok": False, "error": str(e), "format": fmt, "file_path": str(path)}
    except OSError as e:
        return {"ok": False, "error": str(e), "format": fmt, "file_path": str(path)}


def _edit_md_html(path: Path, content: str, fmt: str) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {
        "ok": True,
        "format": fmt,
        "file_path": str(path),
        "bytes_written": len(content.encode("utf-8")),
        "editable": True,
    }


def _edit_docx(path: Path, content: str, content_format: str) -> dict:
    """Replace document body by creating blank doc and inserting md/html."""
    err = _require_sdk()
    if err:
        return {"ok": False, **err}

    created = tool_call("create_doc", {}, timeout=60)
    ready = _ready_created(created, "doc")
    file_id = ready["file_id"]

    cf = (content_format or "md").lower()
    if cf == "html":
        tool_call(
            "doc_insert_html_content",
            {"file_id": file_id, "idx": 0, "html_text": content},
            timeout=180,
        )
    else:
        try:
            tool_call(
                "doc_insert_markdown",
                {"file_id": file_id, "idx": 0, "markdown": content},
                timeout=180,
            )
        except SdkError:
            tool_call(
                "doc_insert_text",
                {"file_id": file_id, "idx": 0, "text": content},
                timeout=180,
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    _save_office(file_id, path)
    return {
        "ok": True,
        "format": "docx",
        "file_path": str(path),
        "file_id": file_id,
        "engine": "editor_sdk",
        "note": "wrote new document from content (create_doc + insert)",
    }


def _edit_xlsx(path: Path, content: str) -> dict:
    """Write CSV-like content into a new sheet starting at A1."""
    err = _require_sdk()
    if err:
        return {"ok": False, **err}

    created = tool_call("create_sheet", {}, timeout=60)
    ready = _ready_created(created, "sheet")
    file_id = ready["file_id"]
    info = tool_call("sheet_get_sheet_info", {"file_id": file_id}, timeout=60)
    sheet_id = "000001"
    if isinstance(info, dict):
        sheets = info.get("sheets") or info.get("sheet_list") or []
        if isinstance(sheets, list) and sheets and isinstance(sheets[0], dict):
            sheet_id = str(sheets[0].get("sheet_id") or sheets[0].get("id") or sheet_id)

    raw_lines = [ln for ln in content.replace("\r\n", "\n").split("\n") if ln != ""]
    rows = [line.split("\t") if "\t" in line else _split_csv_line(line) for line in raw_lines]
    if not rows:
        rows = [[""]]
    width = max(len(r) for r in rows)
    norm = [r + [""] * (width - len(r)) for r in rows[:500]]
    csv_data = "\n".join(",".join(_csv_escape(c) for c in row) for row in norm)

    tool_call(
        "sheet_set_range_value_by_csv",
        {
            "file_id": file_id,
            "sheet_id": str(sheet_id),
            "start_row": 0,
            "start_col": 0,
            "csv_data": csv_data,
        },
        timeout=180,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    _save_office(file_id, path)
    return {
        "ok": True,
        "format": "xlsx",
        "file_path": str(path),
        "file_id": file_id,
        "sheet_id": sheet_id,
        "engine": "editor_sdk",
        "rows_written": len(norm),
    }


def _split_csv_line(line: str) -> list[str]:
    if "," not in line:
        return [line]
    parts: list[str] = []
    cur = []
    in_q = False
    for ch in line:
        if ch == '"':
            in_q = not in_q
            continue
        if ch == "," and not in_q:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    parts.append("".join(cur))
    return parts


def _csv_escape(value: str) -> str:
    text = str(value)
    if any(ch in text for ch in (",", '"', "\n")):
        return '"' + text.replace('"', '""') + '"'
    return text


def _edit_pptx(path: Path, content: str) -> dict:
    err = _require_sdk()
    if err:
        return {"ok": False, **err}

    created = tool_call("create_slide", {}, timeout=60)
    ready = _ready_created(created, "slide")
    file_id = ready["file_id"]

    slides = [s.strip() for s in re.split(r"\n(?=#{1,3}\s)", content) if s.strip()]
    if not slides:
        slides = [content]

    for i, block in enumerate(slides[:30]):
        title = ""
        body = block
        m = re.match(r"^#{1,3}\s+(.*)$", block, re.M)
        if m:
            title = m.group(1).strip()
            body = block[m.end() :].strip()
        if i > 0:
            try:
                tool_call(
                    "slide_add_slide",
                    {"file_id": file_id},
                    timeout=60,
                )
            except SdkError:
                try:
                    tool_call("slide_insert_page", {"file_id": file_id}, timeout=60)
                except SdkError:
                    pass
        text = (title + "\n" + body).strip() if title else body
        try:
            tool_call(
                "slide_add_text",
                {
                    "file_id": file_id,
                    "page_index": i,
                    "text": text[:4000],
                    "x": 40,
                    "y": 40,
                    "w": 640,
                    "h": 400,
                },
                timeout=60,
            )
        except SdkError as e:
            return {"ok": False, "error": f"slide_add_text failed: {e}", "file_id": file_id}

    path.parent.mkdir(parents=True, exist_ok=True)
    _save_office(file_id, path)
    return {
        "ok": True,
        "format": "pptx",
        "file_path": str(path),
        "file_id": file_id,
        "engine": "editor_sdk",
        "slides_written": min(len(slides), 30),
    }


def document_edit(file_path: str, content: str, format: str | None = None, content_format: str | None = None) -> dict:
    path = _abs(file_path)
    fmt = detect_format(path, format)
    if fmt == "pdf":
        return {"ok": False, "error": "PDF is view-only; editing not supported", "format": "pdf"}
    try:
        if fmt in ("md", "html"):
            return _edit_md_html(path, content, fmt)
        if fmt == "docx":
            return _edit_docx(path, content, content_format or "md")
        if fmt == "xlsx":
            return _edit_xlsx(path, content)
        if fmt == "pptx":
            return _edit_pptx(path, content)
        return {"ok": False, "error": f"unsupported format: {fmt}"}
    except SdkError as e:
        return {"ok": False, "error": str(e), "format": fmt, "file_path": str(path)}
    except OSError as e:
        return {"ok": False, "error": str(e), "format": fmt, "file_path": str(path)}


def document_convert(
    file_path: str,
    to_format: str,
    output_path: str | None = None,
    from_format: str | None = None,
) -> dict:
    src = _abs(file_path)
    if not src.is_file():
        return {"ok": False, "error": f"file not found: {src}"}
    src_fmt = detect_format(src, from_format)
    dst_fmt = to_format.lower().lstrip(".")
    if dst_fmt not in ("md", "html", "docx", "pptx", "xlsx", "pdf", "csv"):
        return {"ok": False, "error": f"unsupported target format: {dst_fmt}"}

    if output_path:
        dest = _abs(output_path)
    else:
        dest = src.with_suffix("." + ("md" if dst_fmt == "md" else dst_fmt))

    try:
        # md ↔ html
        if src_fmt == "md" and dst_fmt == "html":
            html_body = _md_to_html(src.read_text(encoding="utf-8", errors="replace"))
            dest.write_text(
                "<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>\n"
                + html_body
                + "\n</body></html>\n",
                encoding="utf-8",
            )
            return {"ok": True, "from": src_fmt, "to": dst_fmt, "output_path": str(dest)}

        if src_fmt == "html" and dst_fmt == "md":
            md = _html_to_md(src.read_text(encoding="utf-8", errors="replace"))
            dest.write_text(md, encoding="utf-8")
            return {"ok": True, "from": src_fmt, "to": dst_fmt, "output_path": str(dest)}

        # md/html → office via edit
        if src_fmt in ("md", "html") and dst_fmt in ("docx", "pptx", "xlsx"):
            content = src.read_text(encoding="utf-8", errors="replace")
            result = document_edit(str(dest), content, format=dst_fmt, content_format=src_fmt)
            result.update({"from": src_fmt, "to": dst_fmt, "output_path": str(dest)})
            return result

        # office → md/html via preview text
        if src_fmt in ("docx", "pptx", "xlsx", "pdf") and dst_fmt in ("md", "html"):
            preview = document_preview(str(src), format=src_fmt)
            if not preview.get("ok"):
                return preview
            content = preview.get("content") or ""
            if dst_fmt == "html":
                body = _md_to_html(content) if src_fmt != "html" else content
                dest.write_text(
                    "<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>\n"
                    + body
                    + "\n</body></html>\n",
                    encoding="utf-8",
                )
            else:
                dest.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
            return {
                "ok": True,
                "from": src_fmt,
                "to": dst_fmt,
                "output_path": str(dest),
                "note": "converted from preview text extract",
            }

        # xlsx → csv via save_file
        if src_fmt == "xlsx" and dst_fmt == "csv":
            opened = _open_office(src, "xlsx")
            file_id = opened["file_id"]
            info = tool_call("sheet_get_sheet_info", {"file_id": file_id}, timeout=60)
            sheet_id = "1"
            if isinstance(info, dict):
                sheets = info.get("sheets") or info.get("sheet_list") or []
                if sheets and isinstance(sheets[0], dict):
                    sheet_id = str(sheets[0].get("sheet_id") or sheets[0].get("id") or "1")
            tool_call(
                "save_file",
                {
                    "file_id": file_id,
                    "file_path": str(dest),
                    "output_format": "csv",
                    "sheet_id": sheet_id,
                },
                timeout=180,
            )
            return {"ok": True, "from": src_fmt, "to": "csv", "output_path": str(dest), "sheet_id": sheet_id}

        return {
            "ok": False,
            "error": f"conversion {src_fmt} → {dst_fmt} not implemented",
            "file_path": str(src),
        }
    except SdkError as e:
        return {"ok": False, "error": str(e), "from": src_fmt, "to": dst_fmt}
    except OSError as e:
        return {"ok": False, "error": str(e), "from": src_fmt, "to": dst_fmt}


def sdk_status() -> dict:
    status = ensure_sdk()
    return status


def document_present(
    file_path: str,
    open_browser: bool = True,
    target: str | None = None,
) -> dict:
    """WorkBuddy present_files analogue for md/html WYSIWYG."""
    from preview_server import present_url

    return present_url(file_path, open_browser=open_browser, target=target)
