#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
SESSION="${ECHOMIND_LANGUAGE_TMUX_SESSION:-labcanvas-echomind-language}"
INTERVAL_SECONDS="${ECHOMIND_LANGUAGE_INTERVAL_SECONDS:-21600}"
LOG_DIR="$ROOT/output/wechat_gui_agent/$(date +%F)"
LOG_FILE="$LOG_DIR/echomind-language-scheduler.log"
SCRIPT="$ROOT/agentic_tools/wechat_gui_agent/scripts/echomind_language_scheduler.py"
mkdir -p "$LOG_DIR"
export PYTHONPATH="$ROOT/src:${PYTHONPATH:-}"

start() {
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "EchoMind scheduler already running: $SESSION"
    return 0
  fi
  tmux new-session -d -s "$SESSION" -n scheduler \
    "cd '$ROOT' && exec python3 -u '$SCRIPT' --loop --interval-seconds '$INTERVAL_SECONDS' >> '$LOG_FILE' 2>&1"
  echo "Started EchoMind six-hour scheduler: $SESSION"
}

stop() {
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux kill-session -t "$SESSION"
    echo "Stopped EchoMind scheduler: $SESSION"
  else
    echo "EchoMind scheduler not running: $SESSION"
  fi
}

status() {
  if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "not-running: $SESSION"
    return 1
  fi
  echo "running: $SESSION"
  python3 - "$ROOT/agentic_tools/wechat_gui_agent/.private/echomind-language-schedule.state.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    state = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    state = {}
print(json.dumps({
    "last_run_at": state.get("last_run_at"),
    "interval_seconds": state.get("interval_seconds"),
    "last_delivery_status": (state.get("last_delivery") or {}).get("status"),
}, ensure_ascii=False))
PY
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  *) echo "Usage: $0 start|stop|restart|status" >&2; exit 2 ;;
esac
