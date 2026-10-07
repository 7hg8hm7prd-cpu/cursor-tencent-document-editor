---
name: document-editor
description: >-
  Preview and edit local documents via the Tencent editor_sdk Cursor plugin.
  Markdown/HTML default to WorkBuddy-style visual present (document_present).
  Also supports Word, PowerPoint, Excel, and PDF (preview-only).
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
4. **Programmatic rewrite** → `document_edit`.
5. Office formats → `document_preview` / `document_edit` (editor_sdk).
6. Call `document_sdk_status` if office tools fail.
7. PDF is view-only.
8. Pass absolute paths.

## Tools

| Tool | Purpose |
|------|---------|
| `document_present` | **Default** md/html visual editor (WorkBuddy present) |
| `document_preview` | Text/structure preview for all formats |
| `document_edit` | Write/replace content |
| `document_convert` | Convert formats |
| `document_sdk_status` | Health / start editor_sdk |

## Examples

### Open Markdown visually (default)

```
document_present(file_path="/abs/notes.md")
```

### Open HTML visually

```
document_present(file_path="/abs/outbox/plan.html")
```

### Agent rewrite Markdown without UI

```
document_edit(file_path="/abs/notes.md", content="# Title\n\nbody\n", format="md")
```

### Markdown → Word

```
document_convert(file_path="/abs/notes.md", to_format="docx", output_path="/abs/notes.docx")
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| present URL not opening | Open the returned `url` manually; or set `open_browser=false` |
| 双击仍打开源码 | 跑 `bash plugin/scripts/install-local.sh` 后 Reload Window；确认扩展已启用 |
| 要从预览看源码 | 标题栏「编辑源码」或 `Document Present: 编辑源码` |
| port busy | Set `DOCUMENT_PREVIEW_PORT` |
| editor_sdk not reachable | `document_sdk_status` or start `editor_sdk --port=39099` |
