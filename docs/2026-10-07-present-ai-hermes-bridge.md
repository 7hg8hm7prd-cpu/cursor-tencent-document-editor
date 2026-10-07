# Present AI 改写：Hermes WebUI 桥接

日期：2026-10-07  
状态：已实现

## 目标

Cursor present（md/html）提供 AI 改写。模型调用转发本机 Hermes WebUI。

## 路由

| Present | Hermes |
|---------|--------|
| `GET /api/ai/status` | `GET /health` |
| `POST /api/ai/inline-edit` | `POST /api/md/inline-edit` |
| `POST /api/ai/rewrite` | `POST /api/canvas/rewrite` |

基址：`HERMES_WEBUI_BASE`（默认 `http://127.0.0.1:8787`）。

公共逻辑：`mcp-server/hermes_ai.py`。

## UI

工具条 `ai`（md+html）、`box`（html）。选区 → 指令 → 预览 → 确认。  
块级走 rewrite；否则 inline-edit。经 extension bridge（不可直连 localhost）。

## MCP

`document_ai_rewrite` 复用同一转发逻辑。

## 配置

- `mcp.json` / `install-local.sh` 写入 `HERMES_WEBUI_BASE`
- Hermes 不可达时 UI / MCP 提示「请先启动 Hermes」
