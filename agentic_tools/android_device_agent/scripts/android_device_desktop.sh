#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
VIRTUAL_LAUNCHER="$ROOT/agentic_tools/virtual_desktop/launch_virtual_desktop.sh"
SESSION="${ANDROID_DEVICE_TMUX_SESSION:-labcanvas-android-mix2s}"
NAME="${ANDROID_DEVICE_DESKTOP_NAME:-android-mix2s}"
DISPLAY_ID="${ANDROID_DEVICE_DISPLAY:-:99}"
SCREEN="${ANDROID_DEVICE_SCREEN:-1440x2400x24}"
VNC_PORT="${ANDROID_DEVICE_VNC_PORT:-5929}"
NOVNC_PORT="${ANDROID_DEVICE_NOVNC_PORT:-6129}"
SERIAL="${ANDROID_SERIAL:-}"
ACTION="start"

usage() {
  cat <<'EOF'
Usage:
  android_device_desktop.sh [start|stop|restart|status] [--serial SERIAL]

Starts a dedicated tmux-held noVNC desktop running scrcpy for an Android device.

Environment defaults:
  ANDROID_DEVICE_TMUX_SESSION=labcanvas-android-mix2s
  ANDROID_DEVICE_DISPLAY=:99
  ANDROID_DEVICE_VNC_PORT=5929
  ANDROID_DEVICE_NOVNC_PORT=6129
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    start|stop|restart|status) ACTION="$1"; shift ;;
    --serial) SERIAL="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 3
  fi
}

device_serial() {
  if [[ -n "$SERIAL" ]]; then
    printf '%s\n' "$SERIAL"
    return
  fi
  adb devices | awk 'NR > 1 && $2 == "device" {print $1; exit}'
}

status() {
  echo "tmux session: $SESSION"
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "status: running"
    tmux list-panes -t "$SESSION" -F '#{pane_index}: #{pane_current_command} #{pane_pid}'
  else
    echo "status: stopped"
  fi
  echo "noVNC: http://127.0.0.1:$NOVNC_PORT/vnc_lite.html?host=127.0.0.1&port=$NOVNC_PORT&autoconnect=1&resize=remote"
}

stop_session() {
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux kill-session -t "$SESSION"
    echo "Stopped $SESSION"
  else
    echo "$SESSION is not running"
  fi
}

start_session() {
  need adb
  need scrcpy
  need tmux
  if [[ ! -x "$VIRTUAL_LAUNCHER" ]]; then
    echo "Missing virtual desktop launcher: $VIRTUAL_LAUNCHER" >&2
    exit 4
  fi
  serial="$(device_serial)"
  if [[ -z "$serial" ]]; then
    echo "No authorized Android device found. Check: adb devices -l" >&2
    exit 5
  fi
  if ! adb -s "$serial" get-state >/dev/null 2>&1; then
    echo "Android device is not reachable: $serial" >&2
    exit 6
  fi
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "$SESSION already running"
    status
    return
  fi
  log_dir="$ROOT/output/android_device_agent/$(date +%F)"
  mkdir -p "$log_dir"
  command=$(printf '%q ' \
    "$VIRTUAL_LAUNCHER" \
    --name "$NAME" \
    --display "$DISPLAY_ID" \
    --screen "$SCREEN" \
    --vnc-port "$VNC_PORT" \
    --novnc-port "$NOVNC_PORT" \
    --log-dir "$log_dir" \
    -- \
    scrcpy \
    --serial "$serial" \
    --stay-awake \
    --disable-screensaver \
    --window-title "LabCanvas Android MIX 2S ($serial)" \
    --window-width 540 \
    --window-height 1080)
  tmux new-session -d -s "$SESSION" "cd '$ROOT' && $command; exec bash"
  sleep 2
  status
}

case "$ACTION" in
  start) start_session ;;
  stop) stop_session ;;
  restart) stop_session; start_session ;;
  status) status ;;
esac
