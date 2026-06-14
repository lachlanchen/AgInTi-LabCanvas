#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${JLCMCP_REPO_URL:-https://github.com/hyl64/jlcmcp}"
DEST="${JLCMCP_HOME:-$HOME/.local/share/appautoaction/mcp/jlcmcp}"

mkdir -p "$(dirname "$DEST")"
if [[ -d "$DEST/.git" ]]; then
  git -C "$DEST" pull --ff-only
else
  git clone "$REPO_URL" "$DEST"
fi

npm --prefix "$DEST" install
npm --prefix "$DEST" run build
npm --prefix "$DEST/jlc-bridge" install
npm --prefix "$DEST/jlc-bridge" run build

printf '%s\n%s\n' \
  '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"agenticapp-smoke","version":"0.1.0"}},"id":0}' \
  '{"jsonrpc":"2.0","method":"tools/list","id":1}' \
  | timeout 10s node "$DEST/dist/index.js" >/tmp/jlcmcp-tools-list.jsonl

echo "Installed/build OK: $DEST"
echo "Bridge extension: $DEST/jlc-bridge/build/jlc-bridge.eext"
echo "Smoke output: /tmp/jlcmcp-tools-list.jsonl"
echo "MCP command: node $DEST/dist/index.js"
