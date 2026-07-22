#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
SESSION="${BIORENDER_MCP_TMUX_SESSION:-labcanvas-biorender-mcp}"
HOST="${BIORENDER_MCP_HOST:-127.0.0.1}"
PORT="${BIORENDER_MCP_PORT:-19682}"
TOKEN_FILE="${BIORENDER_TOKEN_FILE:-$ROOT/agentic_tools/biorender_agent/.private/oauth-token.local.json}"
START_URL="${BIORENDER_START_URL:-https://app.biorender.com/gallery/illustrations}"

"$ROOT/agentic_tools/biorender_agent/scripts/start_biorender_browser.sh" "$START_URL" >/dev/null
"$ROOT/agentic_tools/biorender_agent/scripts/open_biorender_url.py" \
  "$START_URL" --close-callbacks >/dev/null

if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux new-session -d -s "$SESSION" \
    "cd '$ROOT' && exec python agentic_tools/biorender_agent/scripts/biorender_mcp_proxy.py --host '$HOST' --port '$PORT'"
fi

for _ in $(seq 1 40); do
  if curl -fsS --max-time 2 "http://$HOST:$PORT/.well-known/oauth-protected-resource" >/dev/null; then
    break
  fi
  sleep 0.25
done

curl -fsS --max-time 3 "http://$HOST:$PORT/.well-known/oauth-protected-resource" >/dev/null

if [[ -s "$TOKEN_FILE" ]]; then
  python "$ROOT/agentic_tools/biorender_agent/scripts/probe_biorender_mcp.py" \
    --url "http://$HOST:$PORT/mcp" --json
else
  printf 'BioRender OAuth token is not enrolled. Run:\n  %s\n' \
    "python agentic_tools/biorender_agent/scripts/biorender_oauth_login.py"
fi

printf 'BioRender MCP:   http://%s:%s/mcp\n' "$HOST" "$PORT"
printf 'BioRender noVNC: http://127.0.0.1:6189/vnc.html?host=127.0.0.1&port=6189&autoconnect=1&resize=scale\n'
