#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
SESSION="${WECHAT_DIRECT_CHATOPS_SESSION:-labcanvas-wechat-direct-chatops}"
CONFIG="${1:-$ROOT/agentic_tools/wechat_gui_agent/.private/lazy-research-direct-chatops.local.json}"
PY="$ROOT/agentic_tools/wechat_gui_agent/.private/wechat_decrypt/.venv/bin/python"
LOG_DIR="$ROOT/output/wechat_gui_agent/$(date +%F)"
mkdir -p "$LOG_DIR"

if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session already running: $SESSION"
  exit 0
fi

tmux new-session -d -s "$SESSION" \
  "cd '$ROOT' && '$PY' -u agentic_tools/wechat_gui_agent/scripts/wechat_direct_chatops.py --config '$CONFIG' --loop --send >> '$LOG_DIR/direct-chatops.log' 2>&1"

echo "Started tmux session: $SESSION"
echo "Log: $LOG_DIR/direct-chatops.log"
echo "Attach: tmux attach -t $SESSION"
