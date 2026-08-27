#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
LAUNCHER="$ROOT/agentic_tools/virtual_desktop/launch_virtual_desktop.sh"

DISPLAY_ID="${MINIMAX_VIDEO_DISPLAY:-:106}"
VNC_PORT="${MINIMAX_VIDEO_VNC_PORT:-5926}"
NOVNC_PORT="${MINIMAX_VIDEO_NOVNC_PORT:-6126}"
CDP_PORT="${MINIMAX_VIDEO_CDP_PORT:-49239}"
PROFILE_DIR="${MINIMAX_VIDEO_PROFILE_DIR:-$HOME/.cache/labcanvas-minimax-video-chrome}"
START_URL="${MINIMAX_VIDEO_START_URL:-https://hailuoai.video/create/image-to-video}"
LOG_DIR="${MINIMAX_VIDEO_LOG_DIR:-$ROOT/output/minimax_video/runtime}"
STACK_NAME="labcanvas-minimax-video"
NOVNC_URL="http://127.0.0.1:${NOVNC_PORT}/vnc.html?host=127.0.0.1&port=${NOVNC_PORT}&autoconnect=1&resize=scale&view_only=0&shared=0&reconnect=0"

usage() {
  printf '%s\n' "Usage: $0 start|recover|status|stop|url|config [--json]"
}

browser_pids() {
  pgrep -u "$(id -u)" -f -- "--user-data-dir=${PROFILE_DIR}" || true
}

cdp_ready() {
  curl -fsS --max-time 2 "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1
}

port_ready() {
  local port="$1"
  ss -ltnH | awk '{print $4}' | grep -Eq "(^|:)${port}$"
}

print_config() {
  if [[ "${1:-}" == "--json" ]]; then
    printf '{\n'
    printf '  "display": "%s",\n' "$DISPLAY_ID"
    printf '  "vnc_port": %s,\n' "$VNC_PORT"
    printf '  "novnc_port": %s,\n' "$NOVNC_PORT"
    printf '  "cdp_port": %s,\n' "$CDP_PORT"
    printf '  "profile_dir": "%s",\n' "$PROFILE_DIR"
    printf '  "start_url": "%s",\n' "$START_URL"
    printf '  "novnc_url": "%s"\n' "$NOVNC_URL"
    printf '}\n'
    return
  fi
  printf 'display=%s\n' "$DISPLAY_ID"
  printf 'vnc=127.0.0.1:%s\n' "$VNC_PORT"
  printf 'novnc=%s\n' "$NOVNC_URL"
  printf 'cdp=http://127.0.0.1:%s\n' "$CDP_PORT"
  printf 'profile=%s\n' "$PROFILE_DIR"
}

start_stack() {
  mkdir -p "$LOG_DIR" "$PROFILE_DIR"
  local args=(
    --name "$STACK_NAME"
    --display "$DISPLAY_ID"
    --screen 1920x1080x24
    --vnc-port "$VNC_PORT"
    --novnc-port "$NOVNC_PORT"
    --log-dir "$LOG_DIR"
  )
  if cdp_ready; then
    "$LAUNCHER" "${args[@]}"
  else
    "$LAUNCHER" "${args[@]}" -- \
      google-chrome \
      "--remote-debugging-port=${CDP_PORT}" \
      --remote-debugging-address=127.0.0.1 \
      "--remote-allow-origins=http://127.0.0.1:${CDP_PORT}" \
      "--user-data-dir=${PROFILE_DIR}" \
      --no-first-run \
      --no-default-browser-check \
      --disable-gpu \
      --disable-dev-shm-usage \
      --window-position=0,0 \
      --window-size=1920,1080 \
      --new-window "$START_URL"
  fi

  local attempt
  for attempt in $(seq 1 30); do
    if cdp_ready; then
      printf 'MiniMax video browser ready.\n%s\n' "$NOVNC_URL"
      return 0
    fi
    sleep 1
  done
  printf 'MiniMax video browser did not expose CDP on %s. See %s.\n' "$CDP_PORT" "$LOG_DIR" >&2
  return 1
}

status_stack() {
  local browser=false vnc=false novnc=false
  cdp_ready && browser=true
  port_ready "$VNC_PORT" && vnc=true
  port_ready "$NOVNC_PORT" && novnc=true
  if [[ "${1:-}" == "--json" ]]; then
    printf '{"browser":%s,"vnc":%s,"novnc":%s,"display":"%s","cdp_port":%s,"novnc_url":"%s"}\n' \
      "$browser" "$vnc" "$novnc" "$DISPLAY_ID" "$CDP_PORT" "$NOVNC_URL"
  else
    printf 'browser=%s vnc=%s novnc=%s\n%s\n' "$browser" "$vnc" "$novnc" "$NOVNC_URL"
  fi
  [[ "$browser" == true && "$vnc" == true && "$novnc" == true ]]
}

kill_pid_file() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 0
  local pid
  pid="$(tr -cd '0-9' < "$pid_file")"
  if [[ -n "$pid" ]]; then
    kill "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
}

stop_stack() {
  local pids
  pids="$(browser_pids)"
  if [[ -n "$pids" ]]; then
    kill $pids 2>/dev/null || true
    sleep 2
    pids="$(browser_pids)"
    [[ -z "$pids" ]] || kill -KILL $pids 2>/dev/null || true
  fi
  pkill -u "$(id -u)" -f "websockify.*127.0.0.1:${NOVNC_PORT}.*127.0.0.1:${VNC_PORT}" 2>/dev/null || true
  pkill -u "$(id -u)" -f "x11vnc -display ${DISPLAY_ID} .* -rfbport ${VNC_PORT}" 2>/dev/null || true
  pkill -u "$(id -u)" -f "Xvfb ${DISPLAY_ID}( |$)" 2>/dev/null || true
  kill_pid_file "$ROOT/output/minimax_video/${STACK_NAME}_${DISPLAY_ID#:}_keep_awake.pid"
  printf 'MiniMax video browser stack stopped; profile preserved at %s.\n' "$PROFILE_DIR"
}

command="${1:-}"
shift || true
case "$command" in
  start|recover) start_stack "$@" ;;
  status) status_stack "$@" ;;
  stop) stop_stack ;;
  url) printf '%s\n' "$NOVNC_URL" ;;
  config) print_config "$@" ;;
  *) usage; exit 2 ;;
esac
