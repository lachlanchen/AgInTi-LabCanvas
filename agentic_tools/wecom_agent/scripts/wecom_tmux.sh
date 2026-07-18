#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
TOOL_ROOT="$ROOT/agentic_tools/wecom_agent"
PRIVATE_ENV="${WECOM_ENV_FILE:-$TOOL_ROOT/.private/wecom.local.env}"

if [[ -f "$PRIVATE_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$PRIVATE_ENV"
  set +a
fi

SESSION="${WECOM_TMUX_SESSION:-labcanvas-wecom}"
QUEUE="${WECOM_TASK_QUEUE:-$TOOL_ROOT/.private/wecom_task_queue.jsonl}"
LOG_DIR="$ROOT/output/wecom/$(date +%F)"
GATEWAY_LOG="$LOG_DIR/gateway.log"
WORKER_LOG="$LOG_DIR/worker.log"
DAILY_LOG="$LOG_DIR/daily.log"
mkdir -p "$LOG_DIR"

usage() {
  echo "Usage: wecom_tmux.sh start|stop|restart|status"
}

require_runtime() {
  [[ -f "$PRIVATE_ENV" ]] || { echo "Missing private config: $PRIVATE_ENV" >&2; return 1; }
  [[ -n "${WECOM_BOT_ID:-}" ]] || { echo "WECOM_BOT_ID is empty in $PRIVATE_ENV" >&2; return 1; }
  [[ -n "${WECOM_BOT_SECRET:-}" ]] || { echo "WECOM_BOT_SECRET is empty in $PRIVATE_ENV" >&2; return 1; }
  [[ -n "${WECOM_LOCAL_API_TOKEN:-}" ]] || { echo "WECOM_LOCAL_API_TOKEN is empty in $PRIVATE_ENV" >&2; return 1; }
  [[ -d "$TOOL_ROOT/node_modules/@wecom/aibot-node-sdk" ]] || {
    echo "Missing Node dependencies. Run: (cd $TOOL_ROOT && npm install)" >&2
    return 1
  }
}

start_stack() {
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Session already running: $SESSION"
    status_stack
    return 0
  fi
  require_runtime
  tmux new-session -d -s "$SESSION" -n gateway \
    "cd '$ROOT' && set -a && source '$PRIVATE_ENV' && set +a && exec node '$TOOL_ROOT/src/bridge.mjs' >> '$GATEWAY_LOG' 2>&1"
  tmux new-window -t "$SESSION" -n worker \
    "cd '$ROOT' && set -a && source '$PRIVATE_ENV' && set +a && exec agentic_tools/wechat_gui_agent/scripts/wechat_worker_guarded_loop.sh --queue '$QUEUE' --chat wecom --loop --send >> '$WORKER_LOG' 2>&1"
  tmux new-window -t "$SESSION" -n daily \
    "cd '$ROOT' && set -a && source '$PRIVATE_ENV' && set +a && exec python3 '$TOOL_ROOT/scripts/wecom_daily_research.py' loop --queue '$QUEUE' >> '$DAILY_LOG' 2>&1"
  echo "Started $SESSION"
  echo "Logs: $LOG_DIR"
}

status_stack() {
  if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Session not running: $SESSION"
    return 1
  fi
  tmux list-windows -t "$SESSION" -F '#{window_name}: #{pane_current_command} pid=#{pane_pid}'
}

action="${1:-status}"
case "$action" in
  start)
    start_stack
    ;;
  stop)
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    echo "Stopped $SESSION"
    ;;
  restart)
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    start_stack
    ;;
  status)
    status_stack
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
