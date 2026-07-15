#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ACTION="${1:-start}"
[[ "$ACTION" =~ ^(start|status|stop|restart)$ ]] || { echo "Usage: $0 [start|status|stop|restart]" >&2; exit 2; }

DISPLAY_ID="${LABCANVAS_STUDIO_DISPLAY:-:94}"
SCREEN="${LABCANVAS_STUDIO_SCREEN:-1920x1080x24}"
VNC_PORT="${LABCANVAS_STUDIO_VNC_PORT:-5914}"
NOVNC_PORT="${LABCANVAS_STUDIO_NOVNC_PORT:-6114}"
CDP_PORT="${LABCANVAS_STUDIO_CDP_PORT:-9444}"
APP_PORT="${LABCANVAS_STUDIO_APP_PORT:-19474}"
PROFILE_DIR="${LABCANVAS_STUDIO_PROFILE:-${XDG_CACHE_HOME:-$HOME/.cache}/labcanvas-studio-chrome}"
STATE_DIR="${LABCANVAS_STUDIO_STATE:-${XDG_STATE_HOME:-$HOME/.local/state}/labcanvas-studio-novnc}"
LOG_DIR="$STATE_DIR/logs"
APP_URL="http://127.0.0.1:$APP_PORT"
CDP_URL="http://127.0.0.1:$CDP_PORT"
NOVNC_URL="http://127.0.0.1:$NOVNC_PORT/vnc_lite.html?host=127.0.0.1&port=$NOVNC_PORT&autoconnect=1&resize=remote"

mkdir -p "$LOG_DIR" "$PROFILE_DIR"

pid_alive() {
  [[ -f "$1" ]] || return 1
  local pid
  pid="$(cat "$1" 2>/dev/null || true)"
  [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null
}

stop_pid() {
  local file="$1"
  if pid_alive "$file"; then
    local pid
    pid="$(cat "$file")"
    kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    for _ in {1..30}; do kill -0 "$pid" 2>/dev/null || break; sleep .1; done
  fi
  rm -f "$file"
}

show_status() {
  printf 'LabCanvas Studio isolated desktop\n'
  printf '  app:     %s (%s)\n' "$APP_URL" "$(curl -fsS "$APP_URL/api/health" >/dev/null 2>&1 && echo ready || echo down)"
  printf '  display: %s (%s)\n' "$DISPLAY_ID" "$(DISPLAY="$DISPLAY_ID" xdpyinfo >/dev/null 2>&1 && echo ready || echo down)"
  printf '  VNC:     127.0.0.1:%s\n' "$VNC_PORT"
  printf '  noVNC:   %s\n' "$NOVNC_URL"
  printf '  CDP:     %s (%s)\n' "$CDP_URL" "$(curl -fsS "$CDP_URL/json/version" >/dev/null 2>&1 && echo ready || echo down)"
  printf '  profile: %s\n' "$PROFILE_DIR"
  printf '  state:   %s\n' "$STATE_DIR"
}

if [[ "$ACTION" == "stop" || "$ACTION" == "restart" ]]; then
  stop_pid "$STATE_DIR/chrome.pid"
  stop_pid "$STATE_DIR/novnc.pid"
  stop_pid "$STATE_DIR/x11vnc.pid"
  stop_pid "$STATE_DIR/xvfb.pid"
  stop_pid "$STATE_DIR/app.pid"
  [[ "$ACTION" == "stop" ]] && { show_status; exit 0; }
fi
[[ "$ACTION" == "status" ]] && { show_status; exit 0; }

for command in Xvfb x11vnc websockify xdpyinfo curl python3; do
  command -v "$command" >/dev/null 2>&1 || { echo "Missing required command: $command" >&2; exit 3; }
done
CHROME="$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)"
[[ -n "$CHROME" ]] || { echo "Chrome or Chromium is required" >&2; exit 3; }

if ! curl -fsS "$APP_URL/api/health" >/dev/null 2>&1; then
  env PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" setsid python3 -m agenticapp web --host 127.0.0.1 --port "$APP_PORT" \
    >"$LOG_DIR/app.log" 2>&1 < /dev/null &
  echo "$!" >"$STATE_DIR/app.pid"
  for _ in {1..120}; do curl -fsS "$APP_URL/api/health" >/dev/null 2>&1 && break; sleep .25; done
fi
curl -fsS "$APP_URL/api/health" >/dev/null || { tail -n 100 "$LOG_DIR/app.log" >&2; exit 4; }

if ! DISPLAY="$DISPLAY_ID" xdpyinfo >/dev/null 2>&1; then
  setsid Xvfb "$DISPLAY_ID" -screen 0 "$SCREEN" -ac -nolisten tcp >"$LOG_DIR/xvfb.log" 2>&1 < /dev/null &
  echo "$!" >"$STATE_DIR/xvfb.pid"
  for _ in {1..40}; do DISPLAY="$DISPLAY_ID" xdpyinfo >/dev/null 2>&1 && break; sleep .25; done
fi
DISPLAY="$DISPLAY_ID" xdpyinfo >/dev/null 2>&1 || { tail -n 100 "$LOG_DIR/xvfb.log" >&2; exit 4; }

if ! ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${VNC_PORT}$"; then
  env DISPLAY="$DISPLAY_ID" setsid x11vnc -display "$DISPLAY_ID" -localhost -nopw -forever -shared -noxdamage \
    -rfbport "$VNC_PORT" -o "$LOG_DIR/x11vnc.log" >"$LOG_DIR/x11vnc.stdout.log" 2>&1 < /dev/null &
  echo "$!" >"$STATE_DIR/x11vnc.pid"
  for _ in {1..40}; do ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${VNC_PORT}$" && break; sleep .25; done
fi

if ! ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${NOVNC_PORT}$"; then
  setsid websockify --web=/usr/share/novnc "127.0.0.1:$NOVNC_PORT" "127.0.0.1:$VNC_PORT" >"$LOG_DIR/novnc.log" 2>&1 < /dev/null &
  echo "$!" >"$STATE_DIR/novnc.pid"
fi

if ! curl -fsS "$CDP_URL/json/version" >/dev/null 2>&1; then
  env DISPLAY="$DISPLAY_ID" setsid "$CHROME" \
    --remote-debugging-address=127.0.0.1 --remote-debugging-port="$CDP_PORT" --remote-allow-origins='*' \
    --user-data-dir="$PROFILE_DIR" --no-first-run --no-default-browser-check --disable-default-apps --disable-sync \
    --disable-background-networking --disable-dev-shm-usage --disable-gpu --ozone-platform=x11 \
    --window-position=0,0 --window-size=1920,1080 "$APP_URL" >"$LOG_DIR/chrome.log" 2>&1 < /dev/null &
  echo "$!" >"$STATE_DIR/chrome.pid"
  for _ in {1..160}; do curl -fsS "$CDP_URL/json/version" >/dev/null 2>&1 && break; sleep .25; done
fi
curl -fsS "$CDP_URL/json/version" >/dev/null || { tail -n 100 "$LOG_DIR/chrome.log" >&2; exit 5; }

cd "$ROOT"
python3 scripts/labcanvas_studio_browser.py open --cdp-url "$CDP_URL" --app-url "$APP_URL" >/dev/null
show_status
