# Tencent Document Editor (Cursor Plugin)

独立 Cursor 插件：在 IDE 内预览 / 编辑本地文档。

| 格式 | 预览 | 编辑 |
|------|------|------|
| Markdown (`.md`) | 默认可视化 present | WYSIWYG + MCP `document_edit` |
| HTML (`.html`) | 默认可视化 present | WYSIWYG + MCP `document_edit` |
| Word (`.docx`) | editor_sdk | 整篇重写 |
| PowerPoint (`.pptx`) | editor_sdk | 按章节写幻灯片 |
| Excel (`.xlsx`) | editor_sdk | CSV/TSV 写入 |
| PDF (`.pdf`) | 文本抽取 | 否 |

MD/HTML 对齐 WorkBuddy `present_files`：

- **IDE**：双击默认打开可视化预览（扩展 `tencentDocument.present`）。`Cmd/Ctrl+S` 写回磁盘。「编辑源码」切回文本编辑器。
- **Agent**：MCP 工具 `document_present`（默认端口 `39110`）。

本仓库**不依赖** tax-hermes WebUI。Office 能力需要本机 `editor_sdk` 二进制（不随仓库分发）。

## 目录

```
.
├── .cursor-plugin/plugin.json
├── mcp.json
├── extension/           # Cursor 自定义编辑器（md/html → present）
├── mcp-server/          # Python MCP + present 服务
├── editor-sdk-bridge/   # Node CLI 薄封装
├── skills/ document-editor
├── rules/               # Agent 默认规则
├── scripts/install-local.sh
├── docs/                # 设计说明
└── tests/
```

## 依赖

- Python 3.10+
- Cursor（桌面版）
- 可选：`editor_sdk`（Word/PPT/Excel）
- 可选：`pdftotext` 或 `pypdf`（PDF 预览）

## 安装

```bash
git clone <this-repo>
cd cursor-tencent-document-editor
bash scripts/install-local.sh
```

可选指定 Office SDK：

```bash
export EDITOR_SDK_BIN=/path/to/editor_sdk
bash scripts/install-local.sh
```

然后在 Cursor 执行 **Developer: Reload Window**。

确认：

1. Customize → MCP 有 `document-editor`
2. 扩展列表有 `Tencent Document Present`
3. 双击 `.md` / `.html` → 可视化预览（不是纯源码）

## 手动冒烟

```bash
python3 mcp-server/cli.py status
python3 mcp-server/cli.py present /path/to/notes.md --target cursor
python3 -m unittest discover -s tests -v
```

## 设计文档

- [docs/2026-10-07-document-present-default-editor.md](docs/2026-10-07-document-present-default-editor.md)
- [docs/2026-10-07-document-present-toolbar-parity.md](docs/2026-10-07-document-present-toolbar-parity.md)

## License

MIT（见 [LICENSE](LICENSE)）。`editor_sdk` 二进制及其协议不在本仓库范围内。
