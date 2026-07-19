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
WECOM_WORKER="$TOOL_ROOT/scripts/wecom_worker_loop.sh"
DAILY_LOG="$LOG_DIR/daily.log"
CLI_BRIDGE_CONFIG="$TOOL_ROOT/.private/wecom_cli_bridge.local.json"
CLI_BRIDGE_LOG="$LOG_DIR/external-cli.log"
CLI_TRANSPORT_GUARD="$TOOL_ROOT/scripts/wecom_cli_transport_guard.py"
GUI_BRIDGE_CONFIG="$TOOL_ROOT/.private/wecom_gui_bridge.local.json"
GUI_BRIDGE="$TOOL_ROOT/scripts/wecom_gui_bridge.py"
GUI_BRIDGE_LOG="$LOG_DIR/external-gui.log"
WINDOWS_CLIENT="$TOOL_ROOT/scripts/wecom_windows_client.sh"
mkdir -p "$LOG_DIR"

usage() {
  echo "Usage: wecom_tmux.sh start|stop|restart|external-restart|gui-restart|status"
}

window_exists() {
  tmux has-session -t "$SESSION:$1" 2>/dev/null
}

ensure_core_windows() {
  if ! window_exists gateway; then
    tmux new-window -t "$SESSION" -n gateway \
      "cd '$ROOT' && set -a && source '$PRIVATE_ENV' && set +a && exec node '$TOOL_ROOT/src/bridge.mjs' >> '$GATEWAY_LOG' 2>&1"
  fi
  if ! window_exists worker; then
    tmux new-window -t "$SESSION" -n worker \
      "cd '$ROOT' && exec '$WECOM_WORKER' >> '$WORKER_LOG' 2>&1"
  fi
  if ! window_exists daily; then
    tmux new-window -t "$SESSION" -n daily \
      "cd '$ROOT' && set -a && source '$PRIVATE_ENV' && set +a && exec python3 '$TOOL_ROOT/scripts/wecom_daily_research.py' loop --queue '$QUEUE' >> '$DAILY_LOG' 2>&1"
  fi
}

gui_enabled() {
  [[ -f "$GUI_BRIDGE_CONFIG" ]] \
    && python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("enabled", True) else 1)' "$GUI_BRIDGE_CONFIG"
}

start_gui_window() {
  if ! gui_enabled; then
    echo "External WeCom GUI relay is not configured or is disabled."
    return 0
  fi
  if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Main WeCom session is not running: $SESSION" >&2
    return 1
  fi
  "$WINDOWS_CLIENT" start --json >> "$GUI_BRIDGE_LOG" 2>&1
  tmux kill-window -t "$SESSION:external-gui" 2>/dev/null || true
  tmux new-window -t "$SESSION" -n external-gui \
    "cd '$ROOT' && exec python3 '$GUI_BRIDGE' --config '$GUI_BRIDGE_CONFIG' loop >> '$GUI_BRIDGE_LOG' 2>&1"
  echo "Started allowlisted external WeCom GUI relay window."
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

external_enabled() {
  [[ -f "$CLI_BRIDGE_CONFIG" ]] \
    && python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("enabled", True) else 1)' "$CLI_BRIDGE_CONFIG"
}

start_external_window() {
  if ! external_enabled; then
    echo "External WeCom transport is not configured or is disabled."
    return 0
  fi
  if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Main WeCom session is not running: $SESSION" >&2
    return 1
  fi
  tmux kill-window -t "$SESSION:external" 2>/dev/null || true
  if [[ ! -f "$TOOL_ROOT/.private/wecom-cli-message-config/bot.enc" ]] \
    || [[ ! -f "$TOOL_ROOT/.private/wecom-cli-message-config/mcp_config.enc" ]]; then
    "$TOOL_ROOT/scripts/wecom_admin_browser.sh" >/dev/null
  fi
  tmux new-window -t "$SESSION" -n external \
    "cd '$ROOT' && set -a && source '$PRIVATE_ENV' && set +a && exec python3 '$CLI_TRANSPORT_GUARD' --config '$CLI_BRIDGE_CONFIG' loop >> '$CLI_BRIDGE_LOG' 2>&1"
  echo "Started separate external WeCom transport window."
}

start_stack() {
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    require_runtime
    ensure_core_windows
    if external_enabled && ! window_exists external; then
      start_external_window
    fi
    if gui_enabled && ! window_exists external-gui; then
      start_gui_window
    fi
    echo "Session running and missing windows repaired: $SESSION"
    status_stack
    return 0
  fi
  require_runtime
  tmux new-session -d -s "$SESSION" -n gateway \
    "cd '$ROOT' && set -a && source '$PRIVATE_ENV' && set +a && exec node '$TOOL_ROOT/src/bridge.mjs' >> '$GATEWAY_LOG' 2>&1"
  ensure_core_windows
  start_external_window
  start_gui_window
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
  external-restart)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      start_external_window
    else
      start_stack
    fi
    ;;
  gui-restart)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      start_gui_window
    else
      start_stack
    fi
    ;;
  status)
    status_stack
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
