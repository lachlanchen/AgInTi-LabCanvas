#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SESSION="${WECHAT_CHATOPS_SESSION:-labcanvas-wechat-chatops}"
CONFIG="${1:-$ROOT/agentic_tools/wechat_gui_agent/.private/lazy-research-chatops.local.json}"
LOG_DIR="$ROOT/output/wechat_gui_agent/$(date +%F)"
mkdir -p "$LOG_DIR"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session already running: $SESSION"
  tmux display-message -p -t "$SESSION" '#S #{pane_current_command}'
  exit 0
fi

tmux new-session -d -s "$SESSION" \
  "cd '$ROOT' && python3 -u agentic_tools/wechat_gui_agent/scripts/wechat_chatops_bridge.py --config '$CONFIG' --loop --send >> '$LOG_DIR/chatops.log' 2>&1"

echo "Started tmux session: $SESSION"
echo "Log: $LOG_DIR/chatops.log"
echo "Attach: tmux attach -t $SESSION"
