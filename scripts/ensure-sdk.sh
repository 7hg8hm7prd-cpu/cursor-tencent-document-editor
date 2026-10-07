#!/usr/bin/env bash
# sessionStart hook: ensure local editor_sdk is up. Fail-open (always allow).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export DOCUMENT_EDITOR_PLUGIN_ROOT="$ROOT"

# Prefer repo-relative binary when plugin lives under tax-hermes/plugin
if [[ -z "${EDITOR_SDK_BIN:-}" ]]; then
  for cand in \
    "$ROOT/../third_party/tencent-editor-sdk/darwin-arm64/editor_sdk" \
    "$ROOT/../third_party/tencent-editor-sdk/darwin-x64/editor_sdk" \
    "$ROOT/../third_party/tencent-editor-sdk/linux-x64/editor_sdk"
  do
    if [[ -x "$cand" ]]; then
      export EDITOR_SDK_BIN="$cand"
      break
    fi
  done
fi

python3 "$ROOT/mcp-server/ensure_sdk.py" >/dev/null 2>&1 || true

# Hooks must emit JSON on stdout. Fail open for sessionStart.
printf '%s\n' '{}'
