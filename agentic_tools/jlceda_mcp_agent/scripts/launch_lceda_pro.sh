#!/usr/bin/env bash
set -euo pipefail

PORT="${LCEDA_PRO_CDP_PORT:-51370}"
PIDFILE="${LCEDA_PRO_PIDFILE:-$HOME/.cache/lceda-pro/lceda-pro.pid}"
LOGFILE="${LCEDA_PRO_LOGFILE:-$HOME/.cache/lceda-pro/lceda-pro.log}"
WRAPPER="${LCEDA_PRO_WRAPPER:-$HOME/.local/bin/lceda-pro}"
RESTART=0
STATUS_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port|--cdp-port)
      PORT="$2"
      shift 2
      ;;
    --restart)
      RESTART=1
      shift
      ;;
    --status)
      STATUS_ONLY=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

cdp_alive() {
  curl -fsS "http://127.0.0.1:${PORT}/json/list" >/dev/null 2>&1
}

status() {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" >/dev/null 2>&1; then
    echo "running pid=$(cat "$PIDFILE")"
  else
    echo "not running by pidfile"
  fi
  pgrep -af "lceda-pro.*remote-debugging-port=${PORT}" || true
  curl -fsS "http://127.0.0.1:${PORT}/json/list" 2>/dev/null \
    | jq -r '.[] | [.type,.title,.url] | @tsv' 2>/dev/null || true
}

if [[ "$STATUS_ONLY" == "1" ]]; then
  status
  exit 0
fi

if [[ "$RESTART" == "1" ]]; then
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" >/dev/null 2>&1; then
    kill "$(cat "$PIDFILE")" || true
    sleep 1
  fi
  pkill -f "$HOME/.local/opt/lceda-pro-.*/lceda-pro/lceda-pro.*remote-debugging-port=${PORT}" 2>/dev/null || true
fi

if cdp_alive; then
  status
  exit 0
fi

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" >/dev/null 2>&1; then
  status
  exit 0
fi

mkdir -p "$(dirname "$PIDFILE")"
EXTRA="--disable-gpu --remote-debugging-port=${PORT} --remote-allow-origins=*"
LCEDA_PRO_EXTRA_ARGS="$EXTRA" nohup setsid "$WRAPPER" > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
sleep 2
status
