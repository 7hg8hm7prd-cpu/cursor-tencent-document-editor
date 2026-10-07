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
2. **可视化打开（含 Office）** → `document_present` first（docx/xlsx/pptx/pdf 走 editor_sdk UI）。
3. **Agent-side 只要文本/结构** → `document_preview`（无头 open_file，不展示 UI）。
4. **Programmatic full rewrite** → `document_edit(mode=rewrite)`（默认）。
5. **Office 就地小改** → `document_patch`（find/replace、set_csv）。
6. **AI 改写** → md/html 用 Present `AI`；Office 划选后点浮层蓝色「AI」（Hermes 内联面板，**无**顶栏 / SDK 原生 AI），或 MCP `document_ai_rewrite`（`file_path` + `selection`/`ranges`）。需本机 Hermes。
7. Call `document_sdk_status` if office tools fail。
8. PDF 可视化只读。
9. Pass absolute paths。
10. ⚠️ `open_file` / `document_preview` **不会**给用户看界面；要展示必须 `document_present`。

## Tools

| Tool | Purpose |
|------|---------|
| `document_present` | **Default** md/html / Office 可视化（含 AI 工具条） |
| `document_preview` | Text/structure preview for all formats |
| `document_edit` | Full write/replace（`mode=rewrite` 默认） |
| `document_patch` | Office 就地编辑（open → ops → save） |
| `document_ai_rewrite` | Hermes 选区改写；Office 可 apply 写回 |
| `document_convert` | Convert formats |
| `document_sdk_status` | Health / start editor_sdk |

## Examples

### Open Markdown visually (default)

```
document_present(file_path="/abs/notes.md")
```

### AI rewrite via Hermes（md/html）

```
document_ai_rewrite(instruction="改短一点", selection="很长的一段…", format="md")
```

### Office AI（WorkBuddy 风格：改写 + find/replace 写回）

```
document_ai_rewrite(
  instruction="改成正式语气",
  selection="这段口语化的原文…",
  file_path="/abs/report.docx",
  apply=true
)
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
