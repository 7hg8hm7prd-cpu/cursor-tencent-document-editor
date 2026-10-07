#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown ↔ HTML codec for document present (WorkBuddy / Hermes md_edit parity).

Stdlib only. Covers headings, lists, tasks, tables, links, images, code,
blockquotes, hr, footnotes / endnotes / notes used by present_ui.html.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser


# ---------------------------------------------------------------------------
# Markdown → HTML
# ---------------------------------------------------------------------------


def _is_table_sep(line: str) -> bool:
    s = line.strip()
    if "|" not in s and not re.match(r"^:?-{3,}:?$", s):
        return False
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    parts = [p.strip() for p in s.split("|")]
    if not parts:
        return False
    return all(re.match(r"^:?-{3,}:?$", p) for p in parts)


def md_to_html(md: str) -> str:
    lines = (md or "").replace("\r\n", "\n").split("\n")
    out: list[str] = []
    in_ul = False
    in_ol = False
    in_code = False
    in_quote = False
    code_buf: list[str] = []
    quote_buf: list[str] = []
    fn_buckets: dict[str, list[tuple[str, str]]] = {
        "footnotes": [],
        "endnotes": [],
        "notes": [],
    }
    i = 0
    n = len(lines)

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def close_quote() -> None:
        nonlocal in_quote, quote_buf
        if not in_quote:
            return
        inner = "<br/>".join(inline(x) for x in quote_buf)
        out.append(f"<blockquote><p>{inner}</p></blockquote>")
        quote_buf = []
        in_quote = False

    def flush_code() -> None:
        nonlocal in_code, code_buf
        out.append("<pre><code>" + html.escape("\n".join(code_buf)) + "</code></pre>")
        code_buf = []
        in_code = False

    while i < n:
        raw = lines[i]

        if raw.strip().startswith("```"):
            close_lists()
            close_quote()
            if in_code:
                flush_code()
            else:
                in_code = True
            i += 1
            continue

        if in_code:
            code_buf.append(raw)
            i += 1
            continue

        fm = re.match(r"^\[\^([^\]]+)\]:\s*(.*)$", raw)
        if fm:
            close_lists()
            close_quote()
            fid = fm.group(1)
            body = fm.group(2)
            if fid.startswith("c"):
                fn_buckets["notes"].append((fid, body))
            elif fid.startswith("e"):
                fn_buckets["endnotes"].append((fid, body))
            else:
                fn_buckets["footnotes"].append((fid, body))
            i += 1
            continue

        if "|" in raw and i + 1 < n and _is_table_sep(lines[i + 1]):
            close_lists()
            close_quote()
            rows: list[str] = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(lines[i])
                i += 1
            if len(rows) >= 2:
                out.append(_pipe_table_html(rows))
            continue

        if re.match(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", raw):
            close_lists()
            close_quote()
            out.append("<hr/>")
            i += 1
            continue

        if raw.lstrip().startswith(">"):
            close_lists()
            if not in_quote:
                in_quote = True
                quote_buf = []
            quote_buf.append(re.sub(r"^>\s?", "", raw.lstrip()))
            i += 1
            continue
        close_quote()

        m = re.match(r"^(#{1,6})\s+(.*)$", raw)
        if m:
            close_lists()
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2).strip())}</h{level}>")
            i += 1
            continue

        task = re.match(r"^[-*]\s+\[([ xX])\]\s+(.*)$", raw)
        if task:
            if not in_ul:
                close_lists()
                out.append("<ul>")
                in_ul = True
            checked = " checked" if task.group(1).lower() == "x" else ""
            out.append(
                f'<li class="task"><input type="checkbox" contenteditable="false"{checked}/> '
                f"{inline(task.group(2))}</li>"
            )
            i += 1
            continue

        if re.match(r"^[-*]\s+", raw):
            if not in_ul:
                close_lists()
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline(re.sub(r'^[-*]\\s+', '', raw))}</li>")
            i += 1
            continue

        if re.match(r"^\d+\.\s+", raw):
            if not in_ol:
                close_lists()
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{inline(re.sub(r'^\\d+\\.\\s+', '', raw))}</li>")
            i += 1
            continue

        if not raw.strip():
            close_lists()
            i += 1
            continue

        close_lists()
        out.append(f"<p>{inline(raw.strip())}</p>")
        i += 1

    close_lists()
    close_quote()
    if in_code:
        flush_code()

    titles = {"footnotes": "脚注", "endnotes": "尾注", "notes": "批注"}
    for kind, items in fn_buckets.items():
        if not items:
            continue
        out.append(f'<h2 class="{kind}-title">{titles[kind]}</h2>')
        out.append(f'<ol class="{kind}">')
        for fid, body in items:
            out.append(
                f'<li data-fn-def="{html.escape(fid, quote=True)}" '
                f'data-fn-body="{html.escape(body, quote=True)}">{inline(body)}</li>'
            )
        out.append("</ol>")

    return "\n".join(out)


def _pipe_table_html(rows: list[str]) -> str:
    def split_row(line: str) -> list[str]:
        s = line.strip()
        if s.startswith("|"):
            s = s[1:]
        if s.endswith("|"):
            s = s[:-1]
        return [c.strip() for c in s.split("|")]

    header = split_row(rows[0])
    body_rows = [r for r in rows[2:] if not _is_table_sep(r)]
    parts = ["<table><thead><tr>"]
    for c in header:
        parts.append(f"<th>{inline(c)}</th>")
    parts.append("</tr></thead><tbody>")
    for r in body_rows:
        cells = split_row(r)
        parts.append("<tr>")
        for idx in range(len(header)):
            cell = cells[idx] if idx < len(cells) else ""
            parts.append(f"<td>{inline(cell)}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def inline(s: str) -> str:
    codes: list[str] = []

    def stash_code(m: re.Match[str]) -> str:
        codes.append(m.group(1))
        return f"\x00C{len(codes) - 1}\x00"

    s = re.sub(r"`([^`]+)`", stash_code, s)
    s = html.escape(s)
    s = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r'<img src="\2" alt="\1"/>', s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(
        r"\[\^([^\]]+)\]",
        r'<sup class="fn-ref md-fn-ref" data-fn="\1">\1</sup>',
        s,
    )
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"<em>\1</em>", s)
    s = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", s)

    def unstash(m: re.Match[str]) -> str:
        return f"<code>{html.escape(codes[int(m.group(1))])}</code>"

    return re.sub(r"\x00C(\d+)\x00", unstash, s)


# ---------------------------------------------------------------------------
# HTML → Markdown
# ---------------------------------------------------------------------------


class _HtmlToMd(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._stack: list[str] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._in_pre = False
        self._pre_buf: list[str] = []
        self._link_href: str | None = None
        self._link_buf: list[str] = []
        self._skip_data = 0
        self._fn_defs: list[tuple[str, str]] = []
        self._fn_li_id: str | None = None
        self._fn_li_attr_body: str | None = None
        self._fn_li_buf: list[str] = []
        self._blockquote = 0
        self._ol_is_fn = False
        self._suppress_heading = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k: (v or "") for k, v in attrs}
        tag = tag.lower()
        if tag in ("script", "style"):
            self._skip_data += 1
            return
        if self._skip_data:
            return

        if tag == "table":
            self._table = []
            return
        if tag == "tr" and self._table is not None:
            self._row = []
            return
        if tag in ("td", "th") and self._row is not None:
            self._cell = []
            return

        if tag == "pre":
            self._in_pre = True
            self._pre_buf = []
            return
        if tag == "br":
            # Keep markdown blockquote markers across soft line breaks.
            self._text("\n> " if self._blockquote else "\n")
            return
        if tag == "hr":
            self.parts.append("\n\n---\n\n")
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            cls = ad.get("class", "")
            if any(x in cls for x in ("footnotes-title", "endnotes-title", "notes-title")):
                self._suppress_heading = True
                self._stack.append(tag)
                return
            level = int(tag[1])
            self.parts.append("\n\n" + "#" * level + " ")
            self._stack.append(tag)
            return
        if tag == "p":
            self.parts.append("\n> " if self._blockquote else "\n\n")
            self._stack.append(tag)
            return
        if tag == "blockquote":
            self._blockquote += 1
            self._stack.append(tag)
            return
        if tag == "ul":
            self._stack.append("ul")
            return
        if tag == "ol":
            cls = ad.get("class", "")
            if any(x in cls.split() for x in ("footnotes", "endnotes", "notes")):
                self._ol_is_fn = True
                self._stack.append("fnlist")
                return
            self._stack.append("ol")
            return
        if tag == "li":
            if self._ol_is_fn or "fnlist" in self._stack:
                self._fn_li_id = ad.get("data-fn-def") or ""
                self._fn_li_attr_body = ad.get("data-fn-body") or ""
                self._fn_li_buf = []
                self._stack.append("fnli")
                return
            prefix = "1. " if "ol" in self._stack else "- "
            self.parts.append("\n" + prefix)
            self._stack.append("li")
            return
        if tag == "input" and ad.get("type") == "checkbox":
            checked = "checked" in ad or ad.get("checked") in ("checked", "true", "")
            mark = "x" if checked else " "
            if self.parts and re.search(r"[-*]\s$", self.parts[-1]):
                self.parts[-1] = re.sub(r"([-*])\s$", rf"\1 [{mark}] ", self.parts[-1])
            elif self.parts and self.parts[-1].endswith("- "):
                self.parts[-1] = self.parts[-1][:-2] + f"- [{mark}] "
            return
        if tag in ("strong", "b"):
            self._text("**")
            self._stack.append("strong")
            return
        if tag in ("em", "i"):
            self._text("*")
            self._stack.append("em")
            return
        if tag in ("del", "s"):
            self._text("~~")
            self._stack.append("del")
            return
        if tag == "code" and not self._in_pre:
            self._text("`")
            self._stack.append("code")
            return
        if tag == "a":
            self._link_href = ad.get("href") or ""
            self._link_buf = []
            self._stack.append("a")
            return
        if tag == "img":
            self._text(f"![{ad.get('alt') or ''}]({ad.get('src') or ''})")
            return
        if tag == "sup" and (
            "fn-ref" in ad.get("class", "") or "md-fn-ref" in ad.get("class", "")
        ):
            self._text(f"[^{ad.get('data-fn') or ''}]")
            return
        if tag == "mark":
            self._stack.append("mark")
            return

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("script", "style"):
            self._skip_data = max(0, self._skip_data - 1)
            return
        if self._skip_data:
            return

        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell).replace("\n", " ").strip())
            self._cell = None
            return
        if tag == "tr" and self._row is not None and self._table is not None:
            self._table.append(self._row)
            self._row = None
            return
        if tag == "table" and self._table is not None:
            self.parts.append("\n\n" + _table_to_md(self._table) + "\n\n")
            self._table = None
            return

        if tag == "pre":
            code = "".join(self._pre_buf).rstrip("\n")
            self.parts.append(f"\n\n```\n{code}\n```\n\n")
            self._in_pre = False
            self._pre_buf = []
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if self._suppress_heading:
                self._suppress_heading = False
            else:
                self.parts.append("\n\n")
            self._pop(tag)
            return
        if tag == "p":
            self.parts.append("\n\n")
            self._pop("p")
            return
        if tag == "blockquote":
            self._blockquote = max(0, self._blockquote - 1)
            self.parts.append("\n\n")
            self._pop("blockquote")
            return
        if tag == "ul":
            self.parts.append("\n")
            self._pop("ul")
            return
        if tag == "ol":
            if "fnlist" in self._stack:
                self._ol_is_fn = False
                self._pop("fnlist")
                return
            self.parts.append("\n")
            self._pop("ol")
            return
        if tag == "li":
            if "fnli" in self._stack:
                fid = self._fn_li_id or ""
                body = (self._fn_li_attr_body or "".join(self._fn_li_buf)).strip()
                if fid:
                    self._fn_defs.append((fid, body))
                self._fn_li_id = None
                self._fn_li_attr_body = None
                self._fn_li_buf = []
                self._pop("fnli")
                return
            self.parts.append("\n")
            self._pop("li")
            return
        if tag in ("strong", "b"):
            self._text("**")
            self._pop("strong")
            return
        if tag in ("em", "i"):
            self._text("*")
            self._pop("em")
            return
        if tag in ("del", "s"):
            self._text("~~")
            self._pop("del")
            return
        if tag == "code" and not self._in_pre:
            self._text("`")
            self._pop("code")
            return
        if tag == "a":
            text = "".join(self._link_buf)
            href = self._link_href or ""
            self._link_href = None
            self._link_buf = []
            self._pop("a")
            self._text(f"[{text}]({href})")
            return
        if tag == "mark":
            self._pop("mark")
            return

    def handle_data(self, data: str) -> None:
        if self._skip_data or self._suppress_heading:
            return
        if self._in_pre:
            self._pre_buf.append(data)
            return
        if self._cell is not None:
            self._cell.append(data)
            return
        if "fnli" in self._stack:
            self._fn_li_buf.append(data)
            return
        if "a" in self._stack and self._link_href is not None:
            self._link_buf.append(data)
            return
        self._text(data)

    def _text(self, s: str) -> None:
        if self._cell is not None:
            self._cell.append(s)
            return
        if "a" in self._stack and self._link_href is not None:
            self._link_buf.append(s)
            return
        if "fnli" in self._stack:
            self._fn_li_buf.append(s)
            return
        self.parts.append(s)

    def _pop(self, tag: str) -> None:
        if tag not in self._stack:
            return
        while self._stack:
            t = self._stack.pop()
            if t == tag:
                break

    def result(self) -> str:
        text = "".join(self.parts)
        if self._fn_defs:
            lines = [f"[^{fid}]: {body}" for fid, body in self._fn_defs]
            text = text.rstrip() + "\n\n" + "\n".join(lines) + "\n"
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"(- \[[ xX]\])\s+", r"\1 ", text)
        return text.strip() + "\n"


def _table_to_md(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm = [r + [""] * (width - len(r)) for r in rows]

    def esc(c: str) -> str:
        return c.replace("|", "\\|").replace("\n", " ").strip()

    header = norm[0]
    lines = [
        "| " + " | ".join(esc(c) for c in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for r in norm[1:]:
        lines.append("| " + " | ".join(esc(c) for c in r) + " |")
    return "\n".join(lines)


def html_to_md(raw_html: str) -> str:
    parser = _HtmlToMd()
    try:
        parser.feed(raw_html or "")
        parser.close()
    except Exception:
        text = re.sub(r"(?is)<script[^>]*>.*?</script>", "", raw_html or "")
        text = re.sub(r"(?is)<style[^>]*>.*?</style>", "", text)
        text = re.sub(r"(?s)<[^>]+>", "", text)
        return html.unescape(text).strip() + "\n"
    return parser.result()
