# MD/HTML 默认可视化预览编辑器（Cursor IDE）

日期：2026-10-07  
状态：已实现（2026-10-07：Webview 改为直嵌 present_ui，不再用 localhost iframe）

## 目标

在 Cursor 里双击打开 `.md` / `.html` 时：

1. **默认**进入可视化预览（present），可直接改并保存。
2. **不需要**先发布、也不需要先调 MCP。
3. 需要改源码时，再切换到文本编辑器。

## 方案

在 `plugin/extension/` 增加 VS Code / Cursor 扩展：

- `customEditors`，`priority: "default"`
- 匹配：`*.html` `*.htm` `*.md` `*.markdown`
- Webview 内嵌 `http://127.0.0.1:39110/edit?...`（现有 present 服务）
- 打开时自动拉起 `preview_daemon.py`（若未运行）
- 命令「编辑源码」：`vscode.openWith` → `default` 文本编辑器

Agent 侧规则不变：对话里仍优先 `document_present`。

## 安装

`plugin/scripts/install-local.sh` 同时：

1. 同步到 `~/.cursor/plugins/local/tencent-document-editor`
2. 安装扩展到 `~/.cursor/extensions/tax-hermes.tencent-document-present-*`

用户需 **Reload Window** 一次。

## 非目标

- 不替换 Office（docx/pptx/xlsx）路径
- 不改 present 服务协议
- 不强制改用户全局 `workbench.editorAssociations`（靠 `priority: default`）
