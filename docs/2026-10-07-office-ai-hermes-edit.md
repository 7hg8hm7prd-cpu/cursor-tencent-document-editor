# Office AI 编辑（Hermes 浮层）

日期：2026-10-07  
状态：已落地（浮层 Hermes AI；顶栏 / SDK 原生 AI 已关闭）

## 产品口径

| 入口 | 状态 |
|------|------|
| Present 顶栏「AI 改写」面板 | **已移除** |
| SDK 原生浮层 AI（`aiEdit` / `_wbchat`） | **已关闭** |
| Hermes 蓝色浮层「AI」 | **唯一 UI 入口** |
| MCP `document_ai_rewrite` | 仍可用（Agent） |

## 用户路径（IDE）

1. Reload Window 后打开 `.docx`。
2. iframe：`http://127.0.0.1:39099/static/doc/pc.html?…&local_edit=1&client=sdk_local`（**无** `_wbchat`）。
3. 划选 → 浮层蓝色 **AI** → 就地填指令 → 预览 → 写入。
4. 白屏救急：`HERMES_SDK_DIRECT=1`（跳过注入，无浮层 AI）。

## 技术要点

| 步骤 | 实现 |
|------|------|
| 加载 | 上游 `:39101` 裸 SDK；公开 `:39099` Node 代理（注入 + WebSocket） |
| SDK AI 开关 | `mqq_inject.js` 设 `__WB_DOCS_FEATURE_LIST__={aiEdit:false}` + CSS 隐藏原生 AI |
| Hermes 浮层 | `float_toolbar_ai.js` 注入蓝色按钮与内联面板 |
| 模型 | Hermes `/api/md/inline-edit`（loopback HMAC） |
| 写回 | `replace_range` / find-replace |

## 文件

| 文件 | 作用 |
|------|------|
| `mcp-server/mqq_inject.js` | `mqq` + 关闭 SDK AI |
| `mcp-server/float_toolbar_ai.js` | Hermes 浮层 AI |
| `mcp-server/sdk_inject_proxy.js` | Node 反代：HTML 注入 + WS |
| `mcp-server/boot_sdk_inject.py` | 启上游 SDK + 注入代理 |
| `mcp-server/office_ai.py` / `hermes_ai.py` | Hermes + 写回 |
| `extension/extension.js` | 精简顶栏 + officeAi 桥 |

## 非目标

- 不接腾讯云端「AI文档助手」
- 不恢复顶栏 AI 改写面板
- 不开启 SDK 原生 `aiEdit`
