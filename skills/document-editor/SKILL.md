---
name: document-editor
description: >-
  Preview and edit local documents via the Tencent editor_sdk Cursor plugin.
  Markdown/HTML default to WorkBuddy-style visual present (document_present).
  Also supports Word, PowerPoint, Excel, and PDF (preview-only).
  AI rewrite forwards to local Hermes WebUI. Office in-place edits use document_patch.
---

# Document Editor (Tencent editor_sdk + MD/HTML present)

## Default for Markdown / HTML

**IDE**：安装扩展后，双击 `.md` / `.html` 默认打开可视化预览。看源码用「编辑源码」或 `Reopen Editor With…` → Text Editor。

**Agent**：WorkBuddy 的 `present_files` 对应：

```
document_present(file_path="/abs/path/notes.md", target="cursor")
```

本地 WYSIWYG（`http://127.0.0.1:39110/edit?...`），`Cmd/Ctrl+S` 写回磁盘。

**Use `document_present` as the DEFAULT** when the user wants to view or edit `.md` / `.html`.

## Instructions

1. Prefer MCP tools from the `document-editor` server.
2. **md/html view-edit** → `document_present` first.
3. **Agent-side read** → `document_preview`.
4. **Programmatic full rewrite** → `document_edit(mode=rewrite)`（默认）。
5. **Office 就地小改** → `document_patch`（find/replace、set_csv）。
6. **AI 改写**（选区/块）→ Present 工具条 `AI`，或 MCP `document_ai_rewrite`。需本机 Hermes（`HERMES_WEBUI_BASE`，默认 `http://127.0.0.1:8787`）。
7. Call `document_sdk_status` if office tools fail.
8. PDF is view-only.
9. Pass absolute paths.

## Tools

| Tool | Purpose |
|------|---------|
| `document_present` | **Default** md/html visual editor（含 AI 工具条，经 Hermes） |
| `document_preview` | Text/structure preview for all formats |
| `document_edit` | Full write/replace（`mode=rewrite` 默认） |
| `document_patch` | Office 就地编辑（open → ops → save） |
| `document_ai_rewrite` | 转发 Hermes 做选区/块改写 |
| `document_convert` | Convert formats |
| `document_sdk_status` | Health / start editor_sdk |

## Examples

### Open Markdown visually (default)

```
document_present(file_path="/abs/notes.md")
```

### AI rewrite via Hermes

```
document_ai_rewrite(instruction="改短一点", selection="很长的一段…", format="md")
```

### Office in-place find/replace

```
document_patch(
  file_path="/abs/report.docx",
  ops=[{"op":"find_replace","find":"旧名","replace":"新名"}]
)
```

### Full rebuild Office (rewrite)

```
document_edit(file_path="/abs/report.docx", content="# Title\n\nbody\n", format="docx", mode="rewrite")
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| present URL not opening | Open the returned `url` manually; or set `open_browser=false` |
| 双击仍打开源码 | 跑 `bash scripts/install-local.sh` 后 Reload Window |
| AI 提示启动 Hermes | 先启动本机 Hermes WebUI；可设 `HERMES_WEBUI_BASE` |
| editor_sdk not reachable | `document_sdk_status` or start `editor_sdk --port=39099` |
| 就要就地改 Office | 用 `document_patch`，不要用 `document_edit(mode=in_place)` 整篇覆盖 |
