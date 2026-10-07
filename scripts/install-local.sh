#!/usr/bin/env bash
# Install this Cursor plugin + VS Code extension locally.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${HOME}/.cursor/plugins/local/tencent-document-editor"

mkdir -p "${HOME}/.cursor/plugins/local"
rsync -a --delete \
  --exclude '.editor-sdk-bin' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.git' \
  "$ROOT/" "$DEST/"

# Resolve editor_sdk (optional; needed for Word/PPT/Excel)
SDK="${EDITOR_SDK_BIN:-}"
if [[ -z "$SDK" || ! -x "$SDK" ]]; then
  SDK=""
  for cand in \
    "$ROOT/third_party/tencent-editor-sdk/darwin-arm64/editor_sdk" \
    "$ROOT/third_party/tencent-editor-sdk/darwin-x64/editor_sdk" \
    "$ROOT/third_party/tencent-editor-sdk/linux-x64/editor_sdk" \
    "${TAX_HERMES_ROOT:-}/third_party/tencent-editor-sdk/darwin-arm64/editor_sdk" \
    "${HOME}/tax-hermes/third_party/tencent-editor-sdk/darwin-arm64/editor_sdk" \
    "${HOME}/tax-hermes/third_party/tencent-editor-sdk/darwin-x64/editor_sdk"
  do
    if [[ -n "$cand" && -x "$cand" ]]; then
      SDK="$(cd "$(dirname "$cand")" && pwd)/$(basename "$cand")"
      break
    fi
  done
fi

if [[ -n "$SDK" ]]; then
  printf '%s\n' "$SDK" > "$DEST/.editor-sdk-bin"
  echo "Pinned EDITOR_SDK_BIN=$SDK"
else
  echo "WARN: editor_sdk not found. MD/HTML present still works."
  echo "      For Office, set EDITOR_SDK_BIN=/path/to/editor_sdk and re-run."
fi

chmod +x "$DEST/scripts/"*.sh "$DEST/mcp-server/"*.py "$DEST/editor-sdk-bridge/index.js" 2>/dev/null || true

MCP_JSON="${HOME}/.cursor/mcp.json"
python3 - "$DEST" "${SDK:-}" "$MCP_JSON" <<'PY'
import json, sys
from pathlib import Path
dest, sdk, mcp_path = sys.argv[1:4]
path = Path(mcp_path)
data = {"mcpServers": {}}
if path.is_file():
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        pass
servers = data.setdefault("mcpServers", {})
env = {
    "EDITOR_SDK_PORT": "39099",
    "DOCUMENT_EDITOR_PLUGIN_ROOT": dest,
    "HERMES_WEBUI_BASE": "http://127.0.0.1:8787",
}
if sdk:
    env["EDITOR_SDK_BIN"] = sdk
servers["document-editor"] = {
    "command": "bash",
    "args": [f"{dest}/scripts/run-mcp.sh"],
    "env": env,
}
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Registered default MCP: document-editor → {mcp_path}")
PY

EXT_SRC="$ROOT/extension"
EXT_ID="tax-hermes.tencent-document-present"
EXT_VER="$(python3 -c "import json; print(json.load(open('$EXT_SRC/package.json'))['version'])")"
EXT_DEST="${HOME}/.cursor/extensions/${EXT_ID}-${EXT_VER}"
mkdir -p "${HOME}/.cursor/extensions"
rm -rf "$EXT_DEST"
mkdir -p "$EXT_DEST"
rsync -a "$EXT_SRC/" "$EXT_DEST/"
python3 - "$DEST" "$EXT_DEST" <<'PY'
import json, sys
from pathlib import Path
plugin_root, ext_dest = Path(sys.argv[1]), Path(sys.argv[2])
pkg_path = ext_dest / "package.json"
pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
props = pkg.setdefault("contributes", {}).setdefault("configuration", {}).setdefault("properties", {})
props.setdefault("tencentDocument.pluginRoot", {})["default"] = str(plugin_root)
pkg_path.write_text(json.dumps(pkg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
meta = {"pluginRoot": str(plugin_root), "installedAt": __import__("datetime").datetime.now().isoformat()}
(ext_dest / ".install-meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
print(f"Installed Cursor extension: {ext_dest}")
PY

python3 - <<'PY'
import json
from pathlib import Path

home = Path.home()
candidates = [
    home / "Library/Application Support/Cursor/User/settings.json",
    home / ".config/Cursor/User/settings.json",
    home / ".cursor/User/settings.json",
]
patterns = (
    ("*.html", "tencentDocument.present"),
    ("*.htm", "tencentDocument.present"),
    ("*.md", "tencentDocument.present"),
    ("*.markdown", "tencentDocument.present"),
)
updated = []
for path in candidates:
    is_legacy = path.parts[-3:] == (".cursor", "User", "settings.json")
    parent_ok = path.parent.is_dir() or path.parent.parent.is_dir()
    if not path.is_file() and not parent_ok and not is_legacy:
        continue
    data = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    assoc = data.setdefault("workbench.editorAssociations", {})
    for pattern, view in patterns:
        assoc[pattern] = view
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    updated.append(str(path))
print("Updated editorAssociations in:")
for u in updated:
    print(" -", u)
PY

echo "Installed to $DEST"
echo "Extension: ${EXT_DEST}"
echo "Reload Cursor window (Developer: Reload Window)."
echo "Then open any .md/.html — default is visual present."
