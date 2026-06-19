#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
PRIVATE_ENV="$ROOT/agentic_tools/wechat_gui_agent/.private/wechat_supervisor.local.env"
if [[ -f "$PRIVATE_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$PRIVATE_ENV"
  set +a
fi
SESSION="${WECHAT_SUPERVISOR_SESSION:-labcanvas-wechat}"
CONFIG="${WECHAT_DIRECT_CONFIG:-$ROOT/agentic_tools/wechat_gui_agent/.private/lazy-research-direct-chatops.local.json}"
CONFIGS="${WECHAT_DIRECT_CONFIGS:-$CONFIG}"
QUEUE="${WECHAT_WORKER_QUEUE:-$ROOT/agentic_tools/wechat_gui_agent/.private/wechat_task_queue.jsonl}"
LOG_DIR="$ROOT/output/wechat_gui_agent/$(date +%F)"
PY="$ROOT/agentic_tools/wechat_gui_agent/.private/wechat_decrypt/.venv/bin/python"
DIRECT_POLL_SECONDS="${WECHAT_DIRECT_POLL_SECONDS:-0.8}"
DIRECT_CATCHUP_POLL_SECONDS="${WECHAT_DIRECT_CATCHUP_POLL_SECONDS:-0.1}"
export WECHAT_DECRYPT_REFRESH_INTERVAL="${WECHAT_DECRYPT_REFRESH_INTERVAL:-1}"
export WECHAT_RESTART_DELAY="${WECHAT_RESTART_DELAY:-2}"
mkdir -p "$LOG_DIR"

if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

CHAT_NAME="${WECHAT_CHAT_NAME:-wechat-chat}"
if [[ -f "$CONFIG" ]]; then
  CHAT_NAME="$("$PY" - <<PY
import json
from pathlib import Path
path = Path("$CONFIG")
try:
    print(json.loads(path.read_text(encoding="utf-8")).get("chat_name") or "$CHAT_NAME")
except Exception:
    print("$CHAT_NAME")
PY
)"
fi

usage() {
  cat <<'EOF'
Usage:
  wechat_supervisor_tmux.sh start|stop|restart|status

Environment:
  WECHAT_SUPERVISOR_SESSION   tmux session name, default labcanvas-wechat
  WECHAT_DIRECT_CONFIG        private direct-chatops JSON config
  WECHAT_DIRECT_CONFIGS       comma-separated private direct-chatops configs
  WECHAT_WORKER_QUEUE         private JSONL worker queue
  WECHAT_MEDIA_SOURCES        optional colon-separated folders to sync
  WECHAT_CHAT_NAME            chat name for media-sync events
EOF
}

action="${1:-start}"
case "$action" in
  start)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      echo "Session already running: $SESSION"
      tmux list-panes -t "$SESSION" -F '#{pane_index}: #{pane_current_command}'
      exit 0
    fi
    tmux new-session -d -s "$SESSION" -n desktop \
      "cd '$ROOT' && while true; do agentic_tools/wechat_gui_agent/scripts/wechat_virtual_desktop.sh; sleep 60; done >> '$LOG_DIR/supervisor-desktop.log' 2>&1"
    tmux split-window -h -t "$SESSION:desktop" \
      "cd '$ROOT' && agentic_tools/wechat_gui_agent/scripts/wechat_restart_loop.sh decrypt-refresh agentic_tools/wechat_gui_agent/scripts/wechat_decrypt_refresh_loop.sh >> '$LOG_DIR/supervisor-decrypt-refresh.log' 2>&1"
    IFS=',' read -r -a DIRECT_CONFIGS <<< "$CONFIGS"
    for direct_config in "${DIRECT_CONFIGS[@]}"; do
      direct_config="$(echo "$direct_config" | xargs)"
      [[ -n "$direct_config" ]] || continue
      direct_name="$(basename "$direct_config" .json | tr -c 'A-Za-z0-9_.-' '-')"
      tmux split-window -h -t "$SESSION:desktop" \
        "cd '$ROOT' && agentic_tools/wechat_gui_agent/scripts/wechat_restart_loop.sh 'direct-chatops-$direct_name' '$PY' -u agentic_tools/wechat_gui_agent/scripts/wechat_direct_chatops.py --config '$direct_config' --worker-queue '$QUEUE' --loop --send --no-decrypt --poll-seconds '$DIRECT_POLL_SECONDS' --catchup-poll-seconds '$DIRECT_CATCHUP_POLL_SECONDS' >> '$LOG_DIR/supervisor-direct-chatops-$direct_name.log' 2>&1"
    done
    tmux split-window -v -t "$SESSION:desktop.1" \
      "cd '$ROOT' && agentic_tools/wechat_gui_agent/scripts/wechat_restart_loop.sh worker python3 -u agentic_tools/wechat_gui_agent/scripts/wechat_task_worker.py --queue '$QUEUE' --loop --send >> '$LOG_DIR/supervisor-worker.log' 2>&1"
    tmux split-window -v -t "$SESSION:desktop.0" \
      "cd '$ROOT' && WECHAT_CHAT_NAME='$CHAT_NAME' agentic_tools/wechat_gui_agent/scripts/wechat_restart_loop.sh media-sync agentic_tools/wechat_gui_agent/scripts/wechat_media_sync_loop.sh >> '$LOG_DIR/supervisor-media-sync.log' 2>&1"
    tmux select-layout -t "$SESSION:desktop" tiled >/dev/null
    echo "Started tmux session: $SESSION"
    echo "Logs: $LOG_DIR"
    echo "Attach: tmux attach -t $SESSION"
    ;;
  stop)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      tmux kill-session -t "$SESSION"
      echo "Stopped tmux session: $SESSION"
    else
      echo "Session not running: $SESSION"
    fi
    ;;
  restart)
    "$0" stop || true
    "$0" start
    ;;
  status)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      echo "running: $SESSION"
      tmux list-panes -t "$SESSION" -F '#{pane_index}: #{pane_current_command} #{pane_pid}'
    else
      echo "not-running: $SESSION"
      exit 1
    fi
    ;;
  --help|-h|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
