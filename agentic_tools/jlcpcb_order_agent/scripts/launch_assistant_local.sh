#!/usr/bin/env bash
set -euo pipefail

ASSISTANT_BIN="${JLCPCB_ASSISTANT_BIN:-$HOME/.local/bin/jlc-assistant}"
APP_DIR="${JLC_ASSISTANT_HOME:-$HOME/.local/opt/jlc-assistant-5.0.69/jlc-assistant}"
APP_PROCESS="$APP_DIR/jlc-assistant"
STATE_DIR="${JLCPCB_ASSISTANT_STATE_DIR:-$HOME/.cache/jlcpcb-order/assistant}"
LOG="${JLCPCB_ASSISTANT_LOG:-$STATE_DIR/assistant.log}"
PIDFILE="${JLCPCB_ASSISTANT_PIDFILE:-$STATE_DIR/assistant.pid}"
DEBUG_PORT="${JLCPCB_ASSISTANT_DEBUG_PORT:-}"
STARTUP_TIMEOUT="${JLCPCB_ASSISTANT_STARTUP_TIMEOUT:-60}"
STABILITY_SECONDS="${JLCPCB_ASSISTANT_STABILITY_SECONDS:-30}"
RESTART=0

usage() {
  cat <<'EOF'
Usage: launch_assistant_local.sh [--restart|--stop|--status]

Starts the official JLC desktop assistant as a detached local process.

Environment:
  JLCPCB_ASSISTANT_BIN         Assistant wrapper path, default ~/.local/bin/jlc-assistant
  JLCPCB_ASSISTANT_DEBUG_PORT  Optional remote debugging port for raw CDP inspection
  JLCPCB_ASSISTANT_LOG         Log path, default ~/.cache/jlcpcb-order/assistant/assistant.log
  JLCPCB_ASSISTANT_USE_SANDBOX Set 1 to try Electron sandbox; default is remote-safe no-sandbox
  JLCPCB_ASSISTANT_EXTRA_ARGS  Additional app flags. Keep empty unless debugging.
EOF
}

pid_is_alive() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

known_pids() {
  if [[ -f "$PIDFILE" ]]; then
    local pid
    pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    if pid_is_alive "$pid"; then
      echo "$pid"
    fi
  fi
  pgrep -f "$APP_PROCESS" 2>/dev/null || true
}

stop_assistant() {
  local pids
  pids="$(known_pids | sort -u | tr '\n' ' ')"
  if [[ -z "$pids" ]]; then
    rm -f "$PIDFILE"
    echo "JLC assistant is not running"
    return 0
  fi
  echo "Stopping JLC assistant: $pids"
  # shellcheck disable=SC2086
  kill $pids >/dev/null 2>&1 || true
  sleep 3
  pids="$(known_pids | sort -u | tr '\n' ' ')"
  if [[ -n "$pids" ]]; then
    # shellcheck disable=SC2086
    kill -9 $pids >/dev/null 2>&1 || true
  fi
  rm -f "$PIDFILE"
}

status_assistant() {
  local pids
  pids="$(known_pids | sort -u | tr '\n' ' ')"
  if [[ -n "$pids" ]]; then
    echo "JLC assistant running: $pids"
  else
    echo "JLC assistant not running"
  fi
  echo "log: $LOG"
  if [[ -n "$DEBUG_PORT" ]] && command -v python3 >/dev/null 2>&1; then
    python3 - "$DEBUG_PORT" <<'PY' || true
import json
import sys
import urllib.request

port = sys.argv[1]
try:
    pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2))
except Exception as exc:
    print(f"cdp: unavailable ({exc})")
else:
    print(f"cdp: {len(pages)} page(s)")
    for page in pages:
        title = page.get("title", "")
        url = page.get("url", "")
        print(f"  - {title} :: {url}")
PY
  fi
}

for arg in "$@"; do
  case "$arg" in
    --restart) RESTART=1 ;;
    --stop) stop_assistant; exit 0 ;;
    --status) status_assistant; exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; usage; exit 2 ;;
  esac
done

mkdir -p "$STATE_DIR"

if [[ ! -x "$ASSISTANT_BIN" ]]; then
  echo "JLC assistant binary is not executable: $ASSISTANT_BIN" >&2
  exit 1
fi

if [[ "$RESTART" == "1" ]]; then
  stop_assistant
else
  existing="$(known_pids | head -n 1)"
  if [[ -n "$existing" ]]; then
    echo "JLC assistant already running: $existing"
    status_assistant
    exit 0
  fi
fi

assistant_args=(--disable-gpu)
if [[ -n "$DEBUG_PORT" ]]; then
  assistant_args+=(--remote-debugging-port="$DEBUG_PORT")
fi
if [[ -n "${JLCPCB_ASSISTANT_EXTRA_ARGS:-}" ]]; then
  read -r -a extra_args <<< "$JLCPCB_ASSISTANT_EXTRA_ARGS"
  assistant_args+=("${extra_args[@]}")
fi

if [[ "${JLCPCB_ASSISTANT_USE_SANDBOX:-0}" != "1" ]]; then
  export JLC_ASSISTANT_NO_SANDBOX="${JLC_ASSISTANT_NO_SANDBOX:-1}"
fi
export JLC_ASSISTANT_EXTRA_ARGS="${assistant_args[*]}"

echo "Starting JLC assistant: $ASSISTANT_BIN"
echo "log: $LOG"
(
  cd "$HOME"
  if command -v setsid >/dev/null 2>&1; then
    nohup setsid "$ASSISTANT_BIN" >>"$LOG" 2>&1 &
  else
    nohup "$ASSISTANT_BIN" >>"$LOG" 2>&1 &
  fi
  echo "$!" >"$PIDFILE"
)

pid="$(cat "$PIDFILE")"
for ((i = 0; i < STARTUP_TIMEOUT; i++)); do
  if ! pid_is_alive "$pid"; then
    echo "JLC assistant exited during startup; see $LOG" >&2
    tail -n 80 "$LOG" >&2 || true
    exit 1
  fi
  if [[ -n "$DEBUG_PORT" ]] && command -v python3 >/dev/null 2>&1; then
    if python3 - "$DEBUG_PORT" >/dev/null 2>&1 <<'PY'; then
import sys
import urllib.request
urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/json/version", timeout=1).read()
PY
      break
    fi
  elif (( i >= 5 )); then
    break
  fi
  sleep 1
done

sleep "$STABILITY_SECONDS"
if ! pid_is_alive "$pid"; then
  echo "JLC assistant did not stay alive after startup; see $LOG" >&2
  tail -n 80 "$LOG" >&2 || true
  exit 1
fi

echo "JLC assistant started and stayed alive: pid=$pid"
status_assistant
