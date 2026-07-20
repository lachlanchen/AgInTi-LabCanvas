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
RETRY_SECONDS="${ANDROID_DEVICE_RETRY_SECONDS:-10}"
SERIAL="${ANDROID_SERIAL:-}"
ACTION="start"
OPEN_WECHAT="0"
WAKE_DEVICE="1"

usage() {
  cat <<'EOF'
Usage:
  android_device_desktop.sh [start|stop|restart|status] [--serial SERIAL] [--open-wechat]

Starts a dedicated tmux-held noVNC desktop running scrcpy for an Android device.

Environment defaults:
  ANDROID_DEVICE_TMUX_SESSION=labcanvas-android-mix2s
  ANDROID_DEVICE_DISPLAY=:99
  ANDROID_DEVICE_VNC_PORT=5929
  ANDROID_DEVICE_NOVNC_PORT=6129

Options:
  --open-wechat       Launch mobile WeChat after starting the mirror.
  --no-wake          Do not wake/dismiss the non-secure keyguard first.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    start|stop|restart|status) ACTION="$1"; shift ;;
    --serial) SERIAL="$2"; shift 2 ;;
    --open-wechat) OPEN_WECHAT="1"; shift ;;
    --no-wake) WAKE_DEVICE="0"; shift ;;
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
  local serial=""
  echo "tmux session: $SESSION"
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "status: running"
    tmux list-panes -t "$SESSION" -F '#{pane_index}: #{pane_current_command} #{pane_pid}'
  else
    echo "status: stopped"
  fi
  serial="$(device_serial 2>/dev/null || true)"
  if [[ -n "$serial" ]] && pgrep -u "${USER:-$(id -un)}" -f "^scrcpy --serial $serial([[:space:]]|$)" >/dev/null 2>&1; then
    echo "mirror: connected ($serial)"
  elif [[ -n "$serial" ]]; then
    echo "mirror: waiting for scrcpy retry ($serial)"
  else
    echo "mirror: waiting for an authorized Android device"
  fi
  echo "noVNC: http://127.0.0.1:$NOVNC_PORT/vnc.html?host=127.0.0.1&port=$NOVNC_PORT&autoconnect=1&resize=scale"
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
  if [[ ! "$RETRY_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
    echo "ANDROID_DEVICE_RETRY_SECONDS must be a positive integer." >&2
    exit 3
  fi
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
  if [[ "$WAKE_DEVICE" == "1" ]]; then
    adb -s "$serial" shell input keyevent 224 >/dev/null 2>&1 || true
    adb -s "$serial" shell wm dismiss-keyguard >/dev/null 2>&1 || true
    adb -s "$serial" shell svc power stayon true >/dev/null 2>&1 || true
  fi
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "$SESSION already running"
    if [[ "$OPEN_WECHAT" == "1" ]]; then
      adb -s "$serial" shell monkey -p com.tencent.mm -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
    fi
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
    --app-match "^scrcpy --serial $serial([[:space:]]|$)" \
    -- \
    scrcpy \
    --serial "$serial" \
    --stay-awake \
    --disable-screensaver \
    --window-title "LabCanvas Android MIX 2S ($serial)" \
    --window-width 540 \
    --window-height 1080)
  tmux new-session -d -s "$SESSION" \
    "cd '$ROOT' && while true; do $command || true; sleep '$RETRY_SECONDS'; done"
  sleep 2
  if [[ "$OPEN_WECHAT" == "1" ]]; then
    adb -s "$serial" shell monkey -p com.tencent.mm -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
  fi
  status
}

case "$ACTION" in
  start) start_session ;;
  stop) stop_session ;;
  restart) stop_session; start_session ;;
  status) status ;;
esac
