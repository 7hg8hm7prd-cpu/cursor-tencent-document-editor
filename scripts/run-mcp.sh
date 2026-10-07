#!/usr/bin/env bash
# MCP stdio launcher for Cursor. Resolves editor_sdk then runs server.py.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export DOCUMENT_EDITOR_PLUGIN_ROOT="$ROOT"

if [[ -z "${EDITOR_SDK_BIN:-}" ]]; then
  # 1) optional pin file written by install-local.sh
  if [[ -f "$ROOT/.editor-sdk-bin" ]]; then
    pin="$(tr -d '[:space:]' < "$ROOT/.editor-sdk-bin")"
    if [[ -n "$pin" && -x "$pin" ]]; then
      export EDITOR_SDK_BIN="$pin"
    fi
  fi
fi

if [[ -z "${EDITOR_SDK_BIN:-}" ]]; then
  candidates=(
    "$ROOT/../third_party/tencent-editor-sdk/darwin-arm64/editor_sdk"
    "$ROOT/../third_party/tencent-editor-sdk/darwin-x64/editor_sdk"
    "$ROOT/../third_party/tencent-editor-sdk/linux-x64/editor_sdk"
    "$ROOT/../third_party/tencent-editor-sdk/linux-arm64/editor_sdk"
    "${TAX_HERMES_ROOT:-}/third_party/tencent-editor-sdk/darwin-arm64/editor_sdk"
    "${HOME}/tax-hermes/third_party/tencent-editor-sdk/darwin-arm64/editor_sdk"
  )
  for cand in "${candidates[@]}"; do
    if [[ -n "$cand" && -x "$cand" ]]; then
      export EDITOR_SDK_BIN="$cand"
      break
    fi
  done
fi

export EDITOR_SDK_PORT="${EDITOR_SDK_PORT:-39099}"
exec python3 "$ROOT/mcp-server/server.py"
