#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
DISPLAY_ID="${DISPLAY:-:98}"
INTERVAL="${VIRTUAL_DESKTOP_KEEP_AWAKE_INTERVAL:-55}"
PID_FILE=""
LOG_FILE=""

usage() {
  cat <<'EOF'
Usage:
  start_keep_awake.sh [--display :N] [--interval SECONDS] --pid-file PATH --log-file PATH

Starts one keep-awake daemon for an isolated virtual desktop. Existing daemons
are reused. The daemon only uses xset; it does not inject keyboard or mouse
events into the application.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --display) DISPLAY_ID="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --pid-file) PID_FILE="$2"; shift 2 ;;
    --log-file) LOG_FILE="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$PID_FILE" || -z "$LOG_FILE" ]]; then
  usage >&2
  exit 2
fi

mkdir -p "$(dirname "$PID_FILE")" "$(dirname "$LOG_FILE")"

if ! command -v xset >/dev/null 2>&1; then
  echo "Missing required command: xset" >&2
  exit 3
fi

if ! DISPLAY="$DISPLAY_ID" XAUTHORITY= xdpyinfo >/dev/null 2>&1; then
  echo "Display is not reachable for keep-awake: $DISPLAY_ID" >&2
  exit 4
fi

"$SCRIPT_DIR/keep_awake.sh" --display "$DISPLAY_ID" --once >>"$LOG_FILE" 2>&1

if [[ -s "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${old_pid:-}" ]] && kill -0 "$old_pid" 2>/dev/null; then
    if [[ -r "/proc/$old_pid/cmdline" ]] && tr '\0' ' ' <"/proc/$old_pid/cmdline" | grep -Fq "keep_awake.sh"; then
      echo "Keep-awake already active on $DISPLAY_ID: pid $old_pid"
      exit 0
    fi
  fi
fi

nohup "$SCRIPT_DIR/keep_awake.sh" --display "$DISPLAY_ID" --interval "$INTERVAL" >>"$LOG_FILE" 2>&1 &
pid="$!"
echo "$pid" >"$PID_FILE"
echo "Started keep-awake on $DISPLAY_ID: pid $pid"
