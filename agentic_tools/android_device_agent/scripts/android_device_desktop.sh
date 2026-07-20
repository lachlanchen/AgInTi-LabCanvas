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
USER_NAME="${USER:-$(id -un)}"
STATE_DIR="${ANDROID_DEVICE_STATE_DIR:-$ROOT/output/android_device_agent}"
DISPLAY_NUMBER="${DISPLAY_ID#:}"
DISPLAY_NUMBER="${DISPLAY_NUMBER%%.*}"
KEEP_AWAKE_PID_FILE="$STATE_DIR/${NAME}_${DISPLAY_NUMBER}_keep_awake.pid"
SERIAL_FILE="$STATE_DIR/${NAME}.serial"

usage() {
  cat <<'EOF'
Usage:
  android_device_desktop.sh [on|off|start|stop|restart|status] [--serial SERIAL] [--open-wechat]

Starts a dedicated tmux-held noVNC desktop running scrcpy for an Android device.

Actions:
  on, start         Wake the phone and start its scrcpy/noVNC desktop.
  off, stop         Stop the complete desktop stack and sleep the phone.
  restart           Perform a complete off/on cycle.
  status            Report mirror, transport, and phone power state.

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
    on|off|start|stop|restart|status) ACTION="$1"; shift ;;
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
  if [[ -s "$SERIAL_FILE" ]]; then
    local saved_serial
    saved_serial="$(cat "$SERIAL_FILE" 2>/dev/null || true)"
    if [[ -n "$saved_serial" ]] && adb -s "$saved_serial" get-state >/dev/null 2>&1; then
      printf '%s\n' "$saved_serial"
      return
    fi
  fi
  adb devices | awk 'NR > 1 && $2 == "device" {print $1; exit}'
}

known_serial() {
  if [[ -n "$SERIAL" ]]; then
    printf '%s\n' "$SERIAL"
  elif [[ -s "$SERIAL_FILE" ]]; then
    cat "$SERIAL_FILE"
  elif command -v adb >/dev/null 2>&1; then
    adb devices | awk 'NR > 1 && $2 == "device" {print $1; exit}'
  fi
}

port_listening() {
  command -v ss >/dev/null 2>&1 &&
    ss -ltnH 2>/dev/null | awk -v suffix=":$1" '$4 ~ (suffix "$") {found=1} END {exit !found}'
}

regex_escape() {
  printf '%s' "$1" | sed 's/[][\\.^$*+?(){}|]/\\&/g'
}

stop_matching_processes() {
  local label="$1"
  local pattern="$2"
  local pid attempt alive
  local -a pids=()
  mapfile -t pids < <(pgrep -u "$USER_NAME" -f "$pattern" 2>/dev/null || true)
  if [[ ${#pids[@]} -eq 0 ]]; then
    return
  fi
  for pid in "${pids[@]}"; do
    if [[ "$pid" != "$$" && "$pid" != "$PPID" ]]; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  for attempt in {1..20}; do
    alive="0"
    for pid in "${pids[@]}"; do
      if kill -0 "$pid" 2>/dev/null; then
        alive="1"
        break
      fi
    done
    [[ "$alive" == "0" ]] && break
    sleep 0.1
  done
  for pid in "${pids[@]}"; do
    kill -KILL "$pid" 2>/dev/null || true
  done
  echo "Stopped $label"
}

phone_power_state() {
  local serial="$1"
  adb -s "$serial" shell dumpsys power 2>/dev/null |
    awk -F= '/mWakefulness=/ {gsub(/^[[:space:]]+/, "", $2); print $2; exit}'
}

status() {
  local serial=""
  local power_state=""
  echo "tmux session: $SESSION"
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "status: running"
    tmux list-panes -t "$SESSION" -F '#{pane_index}: #{pane_current_command} #{pane_pid}'
  else
    echo "status: stopped"
  fi
  serial="$(known_serial 2>/dev/null || true)"
  if [[ -n "$serial" ]] && pgrep -u "$USER_NAME" -f "^([^[:space:]]*/)?scrcpy --serial $(regex_escape "$serial")([[:space:]]|$)" >/dev/null 2>&1; then
    echo "mirror: connected ($serial)"
  elif tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "mirror: waiting for scrcpy retry ($serial)"
  else
    echo "mirror: off"
  fi
  if port_listening "$VNC_PORT" && port_listening "$NOVNC_PORT"; then
    echo "transport: online (VNC $VNC_PORT, noVNC $NOVNC_PORT)"
    echo "noVNC: http://127.0.0.1:$NOVNC_PORT/vnc.html?host=127.0.0.1&port=$NOVNC_PORT&autoconnect=1&resize=scale"
  else
    echo "transport: off"
  fi
  if [[ -n "$serial" ]] && command -v adb >/dev/null 2>&1 && adb -s "$serial" get-state >/dev/null 2>&1; then
    power_state="$(phone_power_state "$serial")"
    echo "phone: ${power_state:-unknown} ($serial)"
    echo "USB stay-awake: $(adb -s "$serial" shell settings get global stay_on_while_plugged_in 2>/dev/null | tr -d '\r')"
  elif [[ -n "$serial" ]]; then
    echo "phone: disconnected ($serial)"
  else
    echo "phone: no saved or authorized device"
  fi
}

sleep_device() {
  local serial="$1"
  if [[ -z "$serial" ]] || ! command -v adb >/dev/null 2>&1 || ! adb -s "$serial" get-state >/dev/null 2>&1; then
    echo "Phone is not connected; desktop stopped without changing phone power."
    return
  fi
  adb -s "$serial" shell svc power stayon false >/dev/null 2>&1 || true
  adb -s "$serial" shell input keyevent 223 >/dev/null 2>&1 || true
  sleep 1
  echo "Phone display: $(phone_power_state "$serial" || true) ($serial)"
}

stop_session() {
  local serial=""
  local escaped_display escaped_keep_awake escaped_serial
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux kill-session -t "$SESSION"
    echo "Stopped $SESSION"
  else
    echo "$SESSION is not running"
  fi
  serial="$(known_serial 2>/dev/null || true)"
  escaped_display="$(regex_escape "$DISPLAY_ID")"
  escaped_keep_awake="$(regex_escape "$ROOT/agentic_tools/virtual_desktop/keep_awake.sh")"
  if [[ -n "$serial" ]]; then
    escaped_serial="$(regex_escape "$serial")"
    stop_matching_processes "scrcpy mirror" "^([^[:space:]]*/)?scrcpy --serial $escaped_serial([[:space:]]|$)"
  fi
  stop_matching_processes "noVNC relay $NOVNC_PORT" \
    "^(([^[:space:]]*/)?python3[[:space:]]+)?([^[:space:]]*/)?websockify[[:space:]].*127\\.0\\.0\\.1:$NOVNC_PORT[[:space:]]+127\\.0\\.0\\.1:$VNC_PORT([[:space:]]|$)"
  stop_matching_processes "x11vnc relay $VNC_PORT" \
    "^([^[:space:]]*/)?x11vnc[[:space:]].*-display[[:space:]]+$escaped_display([[:space:]].*)?-rfbport[[:space:]]+$VNC_PORT([[:space:]]|$)"
  stop_matching_processes "X11 keep-awake loop" \
    "^bash[[:space:]]+$escaped_keep_awake[[:space:]]+--display[[:space:]]+$escaped_display([[:space:]]|$)"
  rm -f "$KEEP_AWAKE_PID_FILE"
  stop_matching_processes "Xvfb display $DISPLAY_ID" \
    "^([^[:space:]]*/)?Xvfb[[:space:]]+$escaped_display([[:space:]]|$)"
  sleep_device "$serial"
}

start_session() {
  local attempt escaped_serial serial
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
  mkdir -p "$STATE_DIR"
  printf '%s\n' "$serial" >"$SERIAL_FILE"
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
    escaped_serial="$(regex_escape "$serial")"
    for attempt in {1..30}; do
      if port_listening "$VNC_PORT" && port_listening "$NOVNC_PORT" &&
        pgrep -u "$USER_NAME" -f "^([^[:space:]]*/)?scrcpy --serial $escaped_serial([[:space:]]|$)" >/dev/null 2>&1; then
        break
      fi
      sleep 0.5
    done
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
  escaped_serial="$(regex_escape "$serial")"
  for attempt in {1..30}; do
    if port_listening "$VNC_PORT" && port_listening "$NOVNC_PORT" &&
      pgrep -u "$USER_NAME" -f "^([^[:space:]]*/)?scrcpy --serial $escaped_serial([[:space:]]|$)" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
  if [[ "$OPEN_WECHAT" == "1" ]]; then
    adb -s "$serial" shell monkey -p com.tencent.mm -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
  fi
  status
}

case "$ACTION" in
  on|start) start_session ;;
  off|stop) stop_session ;;
  restart) stop_session; start_session ;;
  status) status ;;
esac
