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
WECHAT_DISPLAY="${WECHAT_DISPLAY:-:97}"
UNLOCK_WATCHDOG="${WECHAT_UNLOCK_WATCHDOG:-1}"
UNLOCK_INTERVAL="${WECHAT_UNLOCK_INTERVAL:-20}"
UNLOCK_ADB_SERIAL="${WECHAT_UNLOCK_ADB_SERIAL:-${ANDROID_SERIAL:-}}"
UNLOCK_FLUSH_DEFERRED="${WECHAT_UNLOCK_FLUSH_DEFERRED:-1}"
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
MEDIA_CHATS="${WECHAT_MEDIA_CHATS:-}"
if [[ -z "$MEDIA_CHATS" ]]; then
  MEDIA_CHATS="$(WECHAT_DIRECT_CONFIGS_VALUE="$CONFIGS" WECHAT_FALLBACK_CHAT="$CHAT_NAME" "$PY" - <<'PY'
import json
import os
from pathlib import Path

names = []
for item in os.environ.get("WECHAT_DIRECT_CONFIGS_VALUE", "").split(","):
    item = item.strip()
    if not item:
        continue
    try:
        name = json.loads(Path(item).read_text(encoding="utf-8")).get("chat_name")
    except Exception:
        name = ""
    if name and name not in names:
        names.append(name)
print(",".join(names) or os.environ.get("WECHAT_FALLBACK_CHAT", "wechat-chat"))
PY
)"
fi

usage() {
  cat <<'EOF'
Usage:
  wechat_supervisor_tmux.sh start|stop|restart|reload-workers|restart-all|status

Notes:
  restart/reload-workers keeps the WeChat GUI desktop alive and only reloads
  monitor, worker, and media-sync windows. Use restart-all, or stop then start,
  only when you intentionally want to restart the official WeChat client.

Environment:
  WECHAT_SUPERVISOR_SESSION   tmux session name, default labcanvas-wechat
  WECHAT_DIRECT_CONFIG        private direct-chatops JSON config
  WECHAT_DIRECT_CONFIGS       comma-separated private direct-chatops configs
  WECHAT_WORKER_QUEUE         private JSONL worker queue
  WECHAT_MEDIA_SOURCES        optional colon-separated folders to sync
  WECHAT_MEDIA_CHATS          optional comma-separated chat names to mirror
  WECHAT_CHAT_NAME            fallback chat name for media-sync events
  WECHAT_UNLOCK_WATCHDOG      1 to keep desktop WeChat unlocked by phone UI, default 1
  WECHAT_UNLOCK_ADB_SERIAL    optional Android serial for phone-side unlock
  WECHAT_UNLOCK_INTERVAL      watchdog poll interval, default 20 seconds
EOF
}

list_session_panes() {
  tmux list-windows -t "$SESSION" -F '#{window_id}	#{window_name}' |
    while IFS=$'\t' read -r window_id window_name; do
      [[ -n "$window_id" ]] || continue
      tmux list-panes -t "$window_id" -F "${window_name}.#{pane_index}: #{pane_current_command} #{pane_pid}"
    done
}

respawn_or_new_window() {
  local window_name="$1"
  local command="$2"
  local window_id
  window_id="$(
    tmux list-windows -t "$SESSION" -F '#{window_id}	#{window_name}' |
      awk -F '\t' -v name="$window_name" '$2 == name { print $1; exit }'
  )"
  if [[ -n "$window_id" ]]; then
    tmux respawn-window -k -t "$window_id" "$command"
    echo "Reloaded window: $window_name"
  else
    tmux new-window -t "$SESSION" -n "$window_name" "$command"
    echo "Started missing window: $window_name"
  fi
}

respawn_or_new_pane_by_start_command() {
  local label="$1"
  local needle="$2"
  local command="$3"
  local pane_id
  pane_id="$(
    tmux list-panes -a -F '#{session_name}	#{pane_id}	#{pane_start_command}' |
      awk -F '\t' -v session="$SESSION" -v needle="$needle" '$1 == session && index($3, needle) { print $2; exit }'
  )"
  if [[ -n "$pane_id" ]]; then
    tmux respawn-pane -k -t "$pane_id" "$command"
    echo "Reloaded pane: $label"
  else
    tmux new-window -t "$SESSION" -n "$label" "$command"
    echo "Started missing window: $label"
  fi
}

unlock_watchdog_command() {
  local args=(python3 -u agentic_tools/wechat_gui_agent/scripts/wechat_desktop_unlock_watchdog.py --display "$WECHAT_DISPLAY" --interval "$UNLOCK_INTERVAL" --loop)
  if [[ -n "$UNLOCK_ADB_SERIAL" ]]; then
    args+=(--serial "$UNLOCK_ADB_SERIAL")
  fi
  if [[ "$UNLOCK_FLUSH_DEFERRED" != "0" ]]; then
    args+=(--flush-deferred)
  fi
  printf "cd %q && agentic_tools/wechat_gui_agent/scripts/wechat_restart_loop.sh unlock-watchdog " "$ROOT"
  printf "%q " "${args[@]}"
  printf ">> %q 2>&1" "$LOG_DIR/supervisor-unlock-watchdog.log"
}

reload_worker_windows() {
  if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Session not running: $SESSION" >&2
    echo "Use start or restart-all only when you intentionally want to launch the WeChat client." >&2
    return 1
  fi
  respawn_or_new_pane_by_start_command "decrypt-refresh" "wechat_decrypt_refresh_loop.sh" \
    "cd '$ROOT' && agentic_tools/wechat_gui_agent/scripts/wechat_restart_loop.sh decrypt-refresh agentic_tools/wechat_gui_agent/scripts/wechat_decrypt_refresh_loop.sh >> '$LOG_DIR/supervisor-decrypt-refresh.log' 2>&1"
  IFS=',' read -r -a DIRECT_CONFIGS <<< "$CONFIGS"
  for direct_config in "${DIRECT_CONFIGS[@]}"; do
    direct_config="$(echo "$direct_config" | xargs)"
    [[ -n "$direct_config" ]] || continue
    direct_name="$(basename "$direct_config" .json | tr -c 'A-Za-z0-9_.-' '-')"
    respawn_or_new_window "direct-$direct_name" \
      "cd '$ROOT' && agentic_tools/wechat_gui_agent/scripts/wechat_restart_loop.sh 'direct-chatops-$direct_name' '$PY' -u agentic_tools/wechat_gui_agent/scripts/wechat_direct_chatops.py --config '$direct_config' --worker-queue '$QUEUE' --loop --send --no-decrypt --poll-seconds '$DIRECT_POLL_SECONDS' --catchup-poll-seconds '$DIRECT_CATCHUP_POLL_SECONDS' >> '$LOG_DIR/supervisor-direct-chatops-$direct_name.log' 2>&1"
  done
  respawn_or_new_window "worker" \
    "cd '$ROOT' && agentic_tools/wechat_gui_agent/scripts/wechat_restart_loop.sh worker python3 -u agentic_tools/wechat_gui_agent/scripts/wechat_task_worker.py --queue '$QUEUE' --loop --send >> '$LOG_DIR/supervisor-worker.log' 2>&1"
  respawn_or_new_window "media-sync" \
    "cd '$ROOT' && WECHAT_CHAT_NAME='$CHAT_NAME' WECHAT_MEDIA_CHATS='$MEDIA_CHATS' agentic_tools/wechat_gui_agent/scripts/wechat_restart_loop.sh media-sync agentic_tools/wechat_gui_agent/scripts/wechat_media_sync_loop.sh >> '$LOG_DIR/supervisor-media-sync.log' 2>&1"
  if [[ "$UNLOCK_WATCHDOG" != "0" ]]; then
    respawn_or_new_window "unlock-watchdog" "$(unlock_watchdog_command)"
  fi
  tmux select-window -t "$SESSION:desktop" >/dev/null 2>&1 || true
  echo "Reloaded worker/monitor windows without restarting the WeChat desktop."
  echo "Logs: $LOG_DIR"
}

action="${1:-start}"
case "$action" in
  start)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      echo "Session already running: $SESSION"
      list_session_panes
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
      tmux new-window -t "$SESSION" -n "direct-$direct_name" \
        "cd '$ROOT' && agentic_tools/wechat_gui_agent/scripts/wechat_restart_loop.sh 'direct-chatops-$direct_name' '$PY' -u agentic_tools/wechat_gui_agent/scripts/wechat_direct_chatops.py --config '$direct_config' --worker-queue '$QUEUE' --loop --send --no-decrypt --poll-seconds '$DIRECT_POLL_SECONDS' --catchup-poll-seconds '$DIRECT_CATCHUP_POLL_SECONDS' >> '$LOG_DIR/supervisor-direct-chatops-$direct_name.log' 2>&1"
    done
    tmux new-window -t "$SESSION" -n worker \
      "cd '$ROOT' && agentic_tools/wechat_gui_agent/scripts/wechat_restart_loop.sh worker python3 -u agentic_tools/wechat_gui_agent/scripts/wechat_task_worker.py --queue '$QUEUE' --loop --send >> '$LOG_DIR/supervisor-worker.log' 2>&1"
    tmux new-window -t "$SESSION" -n media-sync \
      "cd '$ROOT' && WECHAT_CHAT_NAME='$CHAT_NAME' WECHAT_MEDIA_CHATS='$MEDIA_CHATS' agentic_tools/wechat_gui_agent/scripts/wechat_restart_loop.sh media-sync agentic_tools/wechat_gui_agent/scripts/wechat_media_sync_loop.sh >> '$LOG_DIR/supervisor-media-sync.log' 2>&1"
    if [[ "$UNLOCK_WATCHDOG" != "0" ]]; then
      tmux new-window -t "$SESSION" -n unlock-watchdog "$(unlock_watchdog_command)"
    fi
    tmux select-layout -t "$SESSION:desktop" tiled >/dev/null
    tmux select-window -t "$SESSION:desktop" >/dev/null
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
  reload-workers|restart)
    reload_worker_windows
    ;;
  restart-all)
    "$0" stop || true
    "$0" start
    ;;
  status)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      echo "running: $SESSION"
      list_session_panes
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
