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
LAYOUT_FILE="$STATE_DIR/${NAME}.layout"
DUAL_WINDOW_NAME="${ANDROID_DEVICE_DUAL_WINDOW_NAME:-wecom-virtual}"
DUAL_WINDOW_WIDTH="${ANDROID_DEVICE_DUAL_WINDOW_WIDTH:-680}"
DUAL_WINDOW_HEIGHT="${ANDROID_DEVICE_DUAL_WINDOW_HEIGHT:-1360}"
DUAL_WINDOW_Y="${ANDROID_DEVICE_DUAL_WINDOW_Y:-500}"
DUAL_LEFT_X="${ANDROID_DEVICE_DUAL_LEFT_X:-20}"
DUAL_RIGHT_X="${ANDROID_DEVICE_DUAL_RIGHT_X:-740}"
PRIVATE_SCRCPY="$ROOT/agentic_tools/wechat_gui_agent/.private/external/scrcpy-v4.1/scrcpy"
SCRCPY_OVERRIDE="${ANDROID_DEVICE_SCRCPY_BIN:-}"
CONTROL_LEASE="$ROOT/agentic_tools/android_device_agent/scripts/android_control_lease.py"
CONTROL_LOCK="$ROOT/agentic_tools/wecom_agent/.private/wecom_android_bridge.lock"
CONTROL_PRIORITY="$ROOT/agentic_tools/android_device_agent/.private/android_control_priority.json"

usage() {
  cat <<'EOF'
Usage:
  android_device_desktop.sh [on|off|start|stop|restart|status|dual|single|wechat|wecom] [--serial SERIAL] [--open-wechat]

Starts a dedicated tmux-held noVNC desktop running scrcpy for an Android device.

Actions:
  on, start         Wake the phone and start its scrcpy/noVNC desktop.
  off, stop         Stop the complete desktop stack and sleep the phone.
  restart           Perform a complete off/on cycle.
  status            Report mirror, transport, and phone power state.
  dual              Keep WeChat physical and WeCom virtual side by side.
  single, wecom      Return to the automation-safe physical WeCom mirror.
  wechat             Show WeChat on the physical mirror with media muted.

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
    on|off|start|stop|restart|status|dual|single|wechat|wecom) ACTION="$1"; shift ;;
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

resolve_scrcpy_bin() {
  local candidate=""
  for candidate in "$SCRCPY_OVERRIDE" "$PRIVATE_SCRCPY" "$(command -v scrcpy 2>/dev/null || true)"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  echo "Missing usable scrcpy binary." >&2
  return 1
}

scrcpy_supports_new_display() {
  local help_output
  help_output="$("$1" --help 2>&1)" || return 1
  grep -F -- '--new-display' <<<"$help_output" >/dev/null
}

mute_media() {
  local serial="$1"
  adb -s "$serial" shell media volume --stream 3 --set 0 >/dev/null 2>&1 || \
    adb -s "$serial" shell cmd media_session volume --stream 3 --set 0 >/dev/null 2>&1 || true
}

launch_physical_app() {
  local serial="$1"
  local package="$2"
  python3 "$CONTROL_LEASE" run \
    --lock-path "$CONTROL_LOCK" \
    --priority-path "$CONTROL_PRIORITY" \
    --purpose "mix2s_show:$package" \
    --timeout-seconds 120 \
    --lease-seconds 180 \
    -- adb -s "$serial" shell monkey -p "$package" -c android.intent.category.LAUNCHER 1 \
    >/dev/null
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

stored_layout() {
  local layout="single"
  if [[ -s "$LAYOUT_FILE" ]]; then
    layout="$(cat "$LAYOUT_FILE" 2>/dev/null || true)"
  fi
  if [[ "$layout" != "dual" ]]; then
    layout="single"
  fi
  printf '%s\n' "$layout"
}

save_layout() {
  local layout="$1"
  mkdir -p "$STATE_DIR"
  printf '%s\n' "$layout" >"$LAYOUT_FILE"
  chmod 600 "$LAYOUT_FILE"
}

tmux_window_exists() {
  local window_name="$1"
  tmux list-windows -t "$SESSION" -F '#{window_name}' 2>/dev/null |
    awk -v expected="$window_name" '$0 == expected {found=1} END {exit !found}'
}

dual_process_live() {
  local escaped_serial serial="$1"
  [[ -n "$serial" ]] || return 1
  escaped_serial="$(regex_escape "$serial")"
  pgrep -u "$USER_NAME" -f \
    "^([^[:space:]]*/)?scrcpy --serial $escaped_serial --new-display(=|[[:space:]])" \
    >/dev/null 2>&1
}

dual_activity_state() {
  local serial="$1"
  adb -s "$serial" shell dumpsys activity activities 2>/dev/null |
    python3 -c '
import re
import sys

payload = sys.stdin.read()
markers = list(re.finditer(r"(?m)^Display #(\d+)\b[^\n]*$", payload))
components = {}
for index, marker in enumerate(markers):
    display_id = int(marker.group(1))
    end = markers[index + 1].start() if index + 1 < len(markers) else len(payload)
    section = payload[marker.end():end]
    match = re.search(
        r"mResumedActivity:.*?\su\d+\s+([A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+)",
        section,
    )
    components[display_id] = match.group(1) if match else ""
virtual_ids = [display_id for display_id in components if display_id > 0]
virtual_id = max(virtual_ids) if virtual_ids else -1
physical_package = components.get(0, "").partition("/")[0]
virtual_package = components.get(virtual_id, "").partition("/")[0]
print("|".join((physical_package, str(virtual_id), virtual_package)))
'
}

window_id_by_title() {
  local title="$1"
  DISPLAY="$DISPLAY_ID" xdotool search --name "^$(regex_escape "$title")$" 2>/dev/null |
    tail -n 1 || true
}

tile_dual_windows() {
  local attempt left_title right_title left_window="" right_window=""
  left_title="LabCanvas Android MIX 2S ($1)"
  right_title="LabCanvas WeCom Virtual ($1)"
  for attempt in {1..40}; do
    left_window="$(window_id_by_title "$left_title")"
    right_window="$(window_id_by_title "$right_title")"
    if [[ -n "$left_window" && -n "$right_window" ]]; then
      DISPLAY="$DISPLAY_ID" xdotool windowsize "$left_window" "$DUAL_WINDOW_WIDTH" "$DUAL_WINDOW_HEIGHT"
      DISPLAY="$DISPLAY_ID" xdotool windowmove "$left_window" "$DUAL_LEFT_X" "$DUAL_WINDOW_Y"
      DISPLAY="$DISPLAY_ID" xdotool windowsize "$right_window" "$DUAL_WINDOW_WIDTH" "$DUAL_WINDOW_HEIGHT"
      DISPLAY="$DISPLAY_ID" xdotool windowmove "$right_window" "$DUAL_RIGHT_X" "$DUAL_WINDOW_Y"
      return 0
    fi
    sleep 0.25
  done
  echo "Dual mirror windows did not both become visible." >&2
  return 1
}

ensure_dual_layout() {
  local dual_loop_command review_body review_command scrcpy_bin serial setup_command
  need adb
  need tmux
  need xdotool
  serial="$(device_serial)"
  scrcpy_bin="$(resolve_scrcpy_bin)"
  if ! scrcpy_supports_new_display "$scrcpy_bin"; then
    echo "Dual review requires scrcpy with --new-display support: $scrcpy_bin" >&2
    return 1
  fi
  mute_media "$serial"
  tmux rename-window -t "$SESSION:0" wechat-physical 2>/dev/null || true
  if tmux_window_exists "$DUAL_WINDOW_NAME" && ! dual_process_live "$serial"; then
    tmux kill-window -t "$SESSION:$DUAL_WINDOW_NAME"
  fi
  if ! tmux_window_exists "$DUAL_WINDOW_NAME"; then
    # The mirror is passive after startup. Holding the shared Android lock for
    # its full review lifetime would block scheduled sends and relay polling.
    setup_command=$(printf '%q ' \
      python3 "$CONTROL_LEASE" run \
      --lock-path "$CONTROL_LOCK" \
      --priority-path "$CONTROL_PRIORITY" \
      --purpose mix2s_dual_setup \
      --timeout-seconds 120 \
      --lease-seconds 180 \
      -- adb -s "$serial" shell monkey -p com.tencent.mm -c android.intent.category.LAUNCHER 1)
    review_body='set -e
child_pid=""
cleanup() {
  if [[ "$child_pid" =~ ^[1-9][0-9]*$ ]] && kill -0 "$child_pid" 2>/dev/null; then
    kill -TERM -- "-$child_pid" 2>/dev/null || true
    wait "$child_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT HUP INT TERM
setsid "$@" &
child_pid=$!
wait "$child_pid"'
    review_command=$(printf '%q ' \
      bash -c "$review_body" _ \
      env DISPLAY="$DISPLAY_ID" "$scrcpy_bin" \
      --serial "$serial" \
      --new-display=1080x2160/440 \
      --start-app=com.tencent.wework \
      --no-audio \
      --keyboard=sdk \
      --mouse=sdk \
      --stay-awake \
      --disable-screensaver \
      --window-title "LabCanvas WeCom Virtual ($serial)" \
      --window-x "$DUAL_RIGHT_X" \
      --window-y "$DUAL_WINDOW_Y" \
      --window-width "$DUAL_WINDOW_WIDTH" \
      --window-height "$DUAL_WINDOW_HEIGHT")
    dual_loop_command="while [[ \"\$(cat '$LAYOUT_FILE' 2>/dev/null || true)\" == dual ]]; do $setup_command >/dev/null 2>&1 || true; $review_command || true; sleep '$RETRY_SECONDS'; done"
    tmux new-window -d -t "$SESSION" -n "$DUAL_WINDOW_NAME" \
      "cd '$ROOT' && $dual_loop_command"
  fi
  tile_dual_windows "$serial"
  echo "dual displays: online (WeChat physical, WeCom virtual)"
}

ensure_single_layout() {
  local app_package="${1:-com.tencent.wework}"
  local serial window=""
  need xdotool
  serial="$(known_serial 2>/dev/null || true)"
  if tmux has-session -t "$SESSION" 2>/dev/null && tmux_window_exists "$DUAL_WINDOW_NAME"; then
    tmux kill-window -t "$SESSION:$DUAL_WINDOW_NAME"
  fi
  if [[ -n "$serial" ]]; then
    if [[ "$app_package" == "com.tencent.mm" ]]; then
      mute_media "$serial"
    fi
    launch_physical_app "$serial" "$app_package"
    window="$(window_id_by_title "LabCanvas Android MIX 2S ($serial)")"
  fi
  if [[ -n "$window" ]]; then
    DISPLAY="$DISPLAY_ID" xdotool windowsize "$window" 540 1080
    DISPLAY="$DISPLAY_ID" xdotool windowmove "$window" 450 660
  fi
  echo "dual displays: off"
}

status() {
  local dual_state="" layout serial=""
  local power_state=""
  layout="$(stored_layout)"
  echo "tmux session: $SESSION"
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "status: running"
    tmux list-panes -s -t "$SESSION" -F '#{window_name}:#{pane_index} #{pane_current_command} #{pane_pid}'
  else
    echo "status: stopped"
  fi
  echo "layout: $layout"
  serial="$(known_serial 2>/dev/null || true)"
  if [[ "$layout" == "dual" ]] && tmux has-session -t "$SESSION" 2>/dev/null &&
    tmux_window_exists "$DUAL_WINDOW_NAME" && dual_process_live "$serial"; then
    dual_state="$(dual_activity_state "$serial" 2>/dev/null || true)"
    if [[ "$dual_state" =~ ^com\.tencent\.mm\|[1-9][0-9]*\|com\.tencent\.wework$ ]]; then
      echo "dual displays: online (WeChat physical, WeCom virtual)"
    else
      echo "dual displays: waiting for app restore (${dual_state:-unreadable})"
    fi
  elif [[ "$layout" == "dual" ]]; then
    echo "dual displays: waiting for restore"
  else
    echo "dual displays: off"
  fi
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
  local attempt escaped_serial scrcpy_bin serial
  need adb
  need tmux
  scrcpy_bin="$(resolve_scrcpy_bin)"
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
    --app-match "^([^[:space:]]*/)?scrcpy --serial $serial([[:space:]]|$)" \
    -- \
    "$scrcpy_bin" \
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
  on|start)
    start_session
    if [[ "$(stored_layout)" == "dual" ]]; then
      ensure_dual_layout
    fi
    ;;
  off|stop) stop_session ;;
  restart)
    stop_session
    start_session
    if [[ "$(stored_layout)" == "dual" ]]; then
      ensure_dual_layout
    fi
    ;;
  status) status ;;
  dual)
    save_layout dual
    start_session
    ensure_dual_layout
    status
    ;;
  single)
    save_layout single
    start_session
    ensure_single_layout com.tencent.wework
    status
    ;;
  wechat)
    save_layout single
    start_session
    ensure_single_layout com.tencent.mm
    status
    ;;
  wecom)
    save_layout single
    start_session
    ensure_single_layout com.tencent.wework
    status
    ;;
esac
