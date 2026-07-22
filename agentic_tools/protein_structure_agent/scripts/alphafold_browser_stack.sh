#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-status}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
SOURCE_ROOT="${PROTEIN_STRUCTURE_SOURCE_ROOT:-$REPO_ROOT/external/ProteinStructure}"
WORKSPACE_ROOT="${PROTEIN_STRUCTURE_WORKSPACE:-$(cd "$REPO_ROOT/.." && pwd -P)/ProteinStructure}"
DISPLAY_ID="${PROTEIN_STRUCTURE_DISPLAY:-:87}"
SCREEN="${PROTEIN_STRUCTURE_SCREEN:-1920x1080x24}"
VNC_PORT="${PROTEIN_STRUCTURE_VNC_PORT:-5987}"
NOVNC_PORT="${PROTEIN_STRUCTURE_NOVNC_PORT:-6187}"
CDP_PORT="${PROTEIN_STRUCTURE_CDP_PORT:-9222}"
PROFILE_DIR="${PROTEIN_STRUCTURE_PROFILE:-$HOME/.cache/alphafold-server-chrome}"
SESSION="${PROTEIN_STRUCTURE_TMUX_SESSION:-labcanvas-protein-structure}"
URL="${PROTEIN_STRUCTURE_URL:-https://alphafoldserver.com/}"
LOG_DIR="${PROTEIN_STRUCTURE_LOG_DIR:-$WORKSPACE_ROOT/output/labcanvas_alphafold_browser}"
DESKTOP_LAUNCHER="$REPO_ROOT/agentic_tools/virtual_desktop/launch_virtual_desktop.sh"
CHROME_LAUNCHER="$SOURCE_ROOT/scripts/alphafold_server/launch_chrome_webgl.sh"
NOVNC_URL="http://127.0.0.1:$NOVNC_PORT/vnc.html?host=127.0.0.1&port=$NOVNC_PORT&autoconnect=1&resize=scale"

mkdir -p "$LOG_DIR" "$PROFILE_DIR"

cdp_ready() {
  curl -fsS --max-time 3 "http://127.0.0.1:$CDP_PORT/json/version" >/dev/null 2>&1
}

novnc_ready() {
  curl -fsS --max-time 3 "$NOVNC_URL" >/dev/null 2>&1
}

tmux_ready() {
  tmux has-session -t "$SESSION" 2>/dev/null
}

chrome_matches_profile() {
  pgrep -u "${USER:-$(id -un)}" -f -- "--remote-debugging-port=$CDP_PORT.*--user-data-dir=$PROFILE_DIR" >/dev/null 2>&1
}

fit_windows() {
  command -v xdotool >/dev/null 2>&1 || return 0
  local dimensions width height window
  dimensions="$(env DISPLAY="$DISPLAY_ID" XAUTHORITY= xdotool getdisplaygeometry 2>/dev/null || true)"
  [[ "$dimensions" =~ ^[0-9]+[[:space:]][0-9]+$ ]] || return 0
  read -r width height <<<"$dimensions"
  while IFS= read -r window; do
    [[ -n "$window" ]] || continue
    env DISPLAY="$DISPLAY_ID" XAUTHORITY= xdotool windowmove --sync "$window" 0 0 >/dev/null 2>&1 || true
    env DISPLAY="$DISPLAY_ID" XAUTHORITY= xdotool windowsize --sync "$window" "$width" "$height" >/dev/null 2>&1 || true
  done < <(env DISPLAY="$DISPLAY_ID" XAUTHORITY= xdotool search --onlyvisible --class 'google-chrome|Google-chrome|chromium' 2>/dev/null || true)
}

launch_layers() {
  "$DESKTOP_LAUNCHER" \
    --name protein-structure \
    --display "$DISPLAY_ID" \
    --screen "$SCREEN" \
    --vnc-port "$VNC_PORT" \
    --novnc-port "$NOVNC_PORT" \
    --log-dir "$LOG_DIR" \
    --app-match "--remote-debugging-port=$CDP_PORT.*--user-data-dir=$PROFILE_DIR" \
    -- env PORT="$CDP_PORT" PROFILE_DIR="$PROFILE_DIR" "$CHROME_LAUNCHER" "$URL"
}

supervise() {
  trap 'exit 0' TERM INT
  while true; do
    if ! cdp_ready || ! novnc_ready || ! chrome_matches_profile; then
      launch_layers >>"$LOG_DIR/supervisor.log" 2>&1 || true
    fi
    fit_windows
    sleep 5
  done
}

print_status() {
  printf 'session=%s\n' "$SESSION"
  printf 'tmux=%s\n' "$(tmux_ready && echo ready || echo stopped)"
  printf 'display=%s\n' "$DISPLAY_ID"
  printf 'vnc=127.0.0.1:%s\n' "$VNC_PORT"
  printf 'novnc=%s\n' "$NOVNC_URL"
  printf 'novnc_status=%s\n' "$(novnc_ready && echo ready || echo stopped)"
  printf 'cdp=http://127.0.0.1:%s\n' "$CDP_PORT"
  printf 'cdp_status=%s\n' "$(cdp_ready && echo ready || echo stopped)"
  printf 'profile=%s\n' "$PROFILE_DIR"
  printf 'profile_process=%s\n' "$(chrome_matches_profile && echo ready || echo stopped)"
  printf 'source=%s\n' "$SOURCE_ROOT"
  printf 'workspace=%s\n' "$WORKSPACE_ROOT"
  printf 'logs=%s\n' "$LOG_DIR"
}

start_stack() {
  if tmux_ready && cdp_ready && novnc_ready && chrome_matches_profile; then
    fit_windows
    print_status
    return 0
  fi
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  tmux new-session -d -s "$SESSION" "$(printf '%q' "$0") supervise"
  local deadline=$((SECONDS + 75))
  while (( SECONDS < deadline )); do
    if cdp_ready && novnc_ready && chrome_matches_profile; then
      fit_windows
      print_status
      return 0
    fi
    sleep 1
  done
  print_status
  tail -n 80 "$LOG_DIR/supervisor.log" 2>/dev/null || true
  return 1
}

stop_stack() {
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  pkill -u "${USER:-$(id -un)}" -f -- "--remote-debugging-port=$CDP_PORT.*--user-data-dir=$PROFILE_DIR" 2>/dev/null || true
  pkill -u "${USER:-$(id -un)}" -f -- "x11vnc.*-rfbport $VNC_PORT" 2>/dev/null || true
  pkill -u "${USER:-$(id -un)}" -f -- "websockify.*127\\.0\\.0\\.1:$NOVNC_PORT.*127\\.0\\.0\\.1:$VNC_PORT" 2>/dev/null || true
  pkill -u "${USER:-$(id -un)}" -f -- "Xvfb $DISPLAY_ID( |$)" 2>/dev/null || true
  print_status
}

capture_desktop() {
  local output="${2:-$WORKSPACE_ROOT/alphafold-results/screenshots/labcanvas_alphafold_desktop_$(date -u +%Y%m%dT%H%M%SZ).png}"
  mkdir -p "$(dirname "$output")"
  if command -v import >/dev/null 2>&1; then
    env DISPLAY="$DISPLAY_ID" XAUTHORITY= import -window root "$output"
  elif command -v gnome-screenshot >/dev/null 2>&1; then
    env DISPLAY="$DISPLAY_ID" XAUTHORITY= gnome-screenshot -f "$output"
  else
    echo "Neither ImageMagick import nor gnome-screenshot is installed." >&2
    return 3
  fi
  printf 'screenshot=%s\n' "$output"
}

case "$ACTION" in
  start) start_stack ;;
  restart) stop_stack >/dev/null; start_stack ;;
  stop) stop_stack ;;
  status) print_status ;;
  fit) fit_windows; print_status ;;
  screenshot) capture_desktop "$@" ;;
  supervise) supervise ;;
  *)
    echo "Usage: $0 {start|restart|stop|status|fit|screenshot [OUTPUT]}" >&2
    exit 2
    ;;
esac
