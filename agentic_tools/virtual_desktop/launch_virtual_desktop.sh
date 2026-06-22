#!/usr/bin/env bash
set -euo pipefail

NAME="virtual-gui"
DISPLAY_ID=":98"
SCREEN="1920x1080x24"
VNC_PORT="5908"
NOVNC_PORT="6099"
LOG_DIR="output/virtual_desktop/$(date +%F)"
KEEP_AWAKE="${VIRTUAL_DESKTOP_KEEP_AWAKE:-1}"
KEEP_AWAKE_INTERVAL="${VIRTUAL_DESKTOP_KEEP_AWAKE_INTERVAL:-55}"
OPEN_BROWSER="0"
APP_MATCH=""
APP_COMMAND=()
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
USER_NAME="${USER:-$(id -un)}"

usage() {
  cat <<'EOF'
Usage:
  launch_virtual_desktop.sh [options] -- [app command...]

Options:
  --name NAME          Label for log files. Default: virtual-gui
  --display :N         X display. Default: :98
  --screen WxHxD       Xvfb screen. Default: 1920x1080x24
  --vnc-port PORT      localhost x11vnc port. Default: 5908
  --novnc-port PORT    localhost noVNC/websockify port. Default: 6099
  --log-dir DIR        Log directory. Default: output/virtual_desktop/YYYY-MM-DD
  --app-match TEXT     Do not relaunch app if a matching process is already running.
  --no-keep-awake      Do not disable X11 blanking/DPMS.
  --keep-awake-interval SECONDS
                       Refresh X11 keep-awake state on this interval. Default: 55
  --open-browser       Open Chromium/Chrome app window pointed at noVNC.

Example:
  launch_virtual_desktop.sh --name labview --display :98 --vnc-port 5908 --novnc-port 6099 -- \
    /usr/local/natinst/LabVIEW-2026-64/labview
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) NAME="$2"; shift 2 ;;
    --display) DISPLAY_ID="$2"; shift 2 ;;
    --screen) SCREEN="$2"; shift 2 ;;
    --vnc-port) VNC_PORT="$2"; shift 2 ;;
    --novnc-port) NOVNC_PORT="$2"; shift 2 ;;
    --log-dir) LOG_DIR="$2"; shift 2 ;;
    --app-match) APP_MATCH="$2"; shift 2 ;;
    --no-keep-awake) KEEP_AWAKE="0"; shift ;;
    --keep-awake-interval) KEEP_AWAKE_INTERVAL="$2"; shift 2 ;;
    --open-browser) OPEN_BROWSER="1"; shift ;;
    --help|-h) usage; exit 0 ;;
    --) shift; APP_COMMAND=("$@"); break ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 3
  fi
}

need Xvfb
need x11vnc
need websockify
need xdpyinfo
need xwininfo

mkdir -p "$LOG_DIR"

display_number="${DISPLAY_ID#:}"
display_number="${display_number%%.*}"
socket_path="/tmp/.X11-unix/X$display_number"
lock_path="/tmp/.X$display_number-lock"

if ! DISPLAY="$DISPLAY_ID" XAUTHORITY= xdpyinfo >/dev/null 2>&1; then
  if [[ -S "$socket_path" ]] && ! pgrep -u "$USER_NAME" -f "Xvfb $DISPLAY_ID( |$)" >/dev/null 2>&1; then
    rm -f "$socket_path"
  fi
  if [[ -f "$lock_path" ]] && ! pgrep -u "$USER_NAME" -f "Xvfb $DISPLAY_ID( |$)" >/dev/null 2>&1; then
    rm -f "$lock_path"
  fi
  echo "Starting Xvfb $DISPLAY_ID with $SCREEN"
  env XAUTHORITY= setsid Xvfb "$DISPLAY_ID" -screen 0 "$SCREEN" -ac >"$LOG_DIR/${NAME}_xvfb.log" 2>&1 < /dev/null &
  sleep 2
fi

if ! DISPLAY="$DISPLAY_ID" XAUTHORITY= xdpyinfo >/dev/null 2>&1; then
  echo "Display $DISPLAY_ID is not reachable." >&2
  tail -n 80 "$LOG_DIR/${NAME}_xvfb.log" 2>/dev/null || true
  exit 4
fi

if [[ "$KEEP_AWAKE" == "1" ]]; then
  state_dir="$(dirname "$LOG_DIR")"
  mkdir -p "$state_dir"
  keep_awake_id="${DISPLAY_ID#:}"
  keep_awake_id="${keep_awake_id//[^A-Za-z0-9_.-]/_}"
  "$SCRIPT_DIR/start_keep_awake.sh" \
    --display "$DISPLAY_ID" \
    --interval "$KEEP_AWAKE_INTERVAL" \
    --pid-file "$state_dir/${NAME}_${keep_awake_id}_keep_awake.pid" \
    --log-file "$LOG_DIR/${NAME}_keep_awake.log" || true
fi

if ! ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${VNC_PORT}$"; then
  echo "Starting x11vnc on 127.0.0.1:$VNC_PORT for $DISPLAY_ID"
  env -u WAYLAND_DISPLAY x11vnc -display "$DISPLAY_ID" -localhost -nopw -forever -shared -rfbport "$VNC_PORT" \
    -bg -o "$LOG_DIR/${NAME}_x11vnc.log" >/dev/null
fi

if ! ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${NOVNC_PORT}$"; then
  echo "Starting noVNC on http://127.0.0.1:$NOVNC_PORT/"
  websockify -D --web=/usr/share/novnc --log-file="$LOG_DIR/${NAME}_novnc.log" \
    "127.0.0.1:$NOVNC_PORT" "127.0.0.1:$VNC_PORT"
fi

if [[ ${#APP_COMMAND[@]} -gt 0 ]]; then
  MATCHING_APP_PIDS=""
  if [[ -n "$APP_MATCH" ]]; then
    MATCHING_APP_PIDS="$(pgrep -u "$USER_NAME" -f "$APP_MATCH" | grep -v -E "^($$|$PPID)$" || true)"
  fi
  if [[ -n "$MATCHING_APP_PIDS" ]]; then
    echo "App already running: $APP_MATCH"
  else
    echo "Starting app on $DISPLAY_ID: ${APP_COMMAND[*]}"
    env DISPLAY="$DISPLAY_ID" XAUTHORITY= setsid "${APP_COMMAND[@]}" >"$LOG_DIR/${NAME}_app.log" 2>&1 < /dev/null &
  fi
fi

NOVNC_URL="http://127.0.0.1:$NOVNC_PORT/vnc_lite.html?host=127.0.0.1&port=$NOVNC_PORT&autoconnect=1&resize=remote"

if [[ "$OPEN_BROWSER" == "1" ]]; then
  if command -v google-chrome >/dev/null 2>&1; then
    google-chrome --user-data-dir="$HOME/.cache/${NAME}-novnc-${NOVNC_PORT}" --no-first-run --disable-gpu \
      --app="$NOVNC_URL" >"$LOG_DIR/${NAME}_chrome.log" 2>&1 &
  elif command -v chromium >/dev/null 2>&1; then
    chromium --user-data-dir="$HOME/.cache/${NAME}-novnc-${NOVNC_PORT}" --no-first-run --disable-gpu \
      --app="$NOVNC_URL" >"$LOG_DIR/${NAME}_chromium.log" 2>&1 &
  fi
fi

echo
echo "Virtual desktop ready"
echo "  display: $DISPLAY_ID"
echo "  screen:  $(DISPLAY="$DISPLAY_ID" XAUTHORITY= xdpyinfo | awk -F: '/dimensions|depth of root window/ {gsub(/^ +/, "", $2); print $1 ":" $2}' | paste -sd ', ' -)"
echo "  vnc:     127.0.0.1:$VNC_PORT"
echo "  noVNC:   $NOVNC_URL"
echo "  awake:   $KEEP_AWAKE"
echo "  logs:    $LOG_DIR"
echo
echo "Windows:"
DISPLAY="$DISPLAY_ID" XAUTHORITY= xwininfo -root -tree | sed -n '1,40p'
