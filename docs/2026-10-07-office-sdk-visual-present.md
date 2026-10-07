# Office 可视化：接入 editor_sdk `/static/*/pc.html`

日期：2026-10-07  
状态：已实现

## 问题

此前 Office 路径只调用 MCP `open_file` / 结构抽取。  
`open_file` **不展示界面**（WorkBuddy 文档已写明）。  
用户在 Cursor 里看不到腾讯 SDK 编辑器。

## 正确路径（对齐 WorkBuddy present_files）

1. 确保 `editor_sdk` 在 `EDITOR_SDK_PORT`（默认 39099）就绪。
2. 打开：

```
http://127.0.0.1:{port}/static/{doc|sheet|slide|pdf}/pc.html
  ?title=...
  &localFilePath=/abs/path
  &globalPadId=<md5(path)>
  &local_edit=1
  &...
```

3. Cursor 扩展用 iframe 嵌入该 URL；MCP `document_present` 返回同一 URL。

## 代码

| 位置 | 作用 |
|------|------|
| `mcp-server/sdk_preview.py` | `build_sdk_preview_url` / `present_office` |
| `preview_server.present_url` | office → `present_office` |
| `extension/extension.js` | 双击 docx 等 → iframe SDK |
| `ensure_sdk.py` | 启动时带 `--cors_origin` |

## 非目标

- 不用自研 HTML 重画 Word/Excel
- PDF 仅 SDK 只读预览
