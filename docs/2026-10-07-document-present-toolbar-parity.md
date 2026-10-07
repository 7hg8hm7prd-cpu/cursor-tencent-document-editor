# Document Present 工具条对齐 WorkBuddy / Hermes 画布

日期：2026-10-07  
状态：已实现  
对照：`static/canvas_tools.js` §toolbar.definitions、`2026-09-27-unified-canvas-tools-design.md`

## 问题

Cursor present 编辑器只有 B / I / List / H1–H3 / P。  
WorkBuddy / Hermes 统一画布对 md/html 有完整编辑项。

## 目标编辑项（按 ends）

| 组 | 按钮 | md | html |
|---|---|---|---|
| hist | 撤销 / 重做 | ✓ | ✓ |
| fmt | B / I | ✓ | ✓ |
| fmt | U / S / 字号 / 对齐 / 颜色 | — | ✓ |
| head | H1 / H2 / H3 | ✓ | ✓ |
| list | 列表 / 待办 | ✓ | ✓ |
| table | 表格 / 行 / 列 / 删行 / 删列 | ✓ | ✓ |
| insert | 链接 / 图片 | ✓ | ✓ |
| note | 脚注 / 尾注 / 批注 | ✓ | ✓ |
| doc | 目录 / 导航 | ✓ | 导航 |
| ai | AI 改写（Hermes） | ✓ | ✓ |
| ai | 框选 | — | ✓ |
| chrome | 源码 / 保存 | ✓ | ✓ |

已实现：AI / 框选经 preview `/api/ai/*` 转发本机 Hermes。  
非目标（本期）：批注泳道、workspace:// 文件选择（图片改为本地上传到同目录）。

## 实现

- UI：`plugin/mcp-server/present_ui.html`（由 preview 服务 `/edit` 下发）
- 保存链路不变：md → html→md；html → splice body
- 扩展 iframe 继续嵌同一 URL

## MD 编解码（2026-10-07 补齐）

`plugin/mcp-server/md_codec.py`：

- md→html：表格、待办、引用、分隔线、图片、脚注/尾注/批注定义
- html→md：同上，供可视保存写回 `.md`
- 工具条 md 端另加：文件链接、引用、分隔、行内代码
