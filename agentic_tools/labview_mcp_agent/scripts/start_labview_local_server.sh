#!/usr/bin/env bash
set -euo pipefail

DISPLAY_ID="${LABVIEW_LOCAL_DISPLAY:-:98}"
SCREEN="${LABVIEW_XVFB_SCREEN:-1920x1080x24}"
VI_SERVER_PORT="${LABVIEW_VI_SERVER_PORT:-3363}"
MCP_HTTP_PORT="${LABVIEW_MCP_HTTP_PORT:-36987}"
ACTIVATION_PORT="${LABVIEW_ACTIVATION_PORT:-23520}"
LOG_DIR="${LABVIEW_LOCAL_LOG_DIR:-output/labview_local_server/$(date +%F)}"
LABVIEW_BIN="${LABVIEW_BIN:-/usr/local/natinst/LabVIEW-2026-64/labview}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$LOG_DIR"

if [[ ! -x "$LABVIEW_BIN" ]]; then
  echo "LabVIEW binary is not executable: $LABVIEW_BIN" >&2
  exit 3
fi

if [[ "${LABVIEW_SKIP_CONFIG:-0}" != "1" ]]; then
  LABVIEW_VI_SERVER_PORT="$VI_SERVER_PORT" "$SCRIPT_DIR/configure_labview_local_server.sh"
fi

display_number="${DISPLAY_ID#:}"
display_number="${display_number%%.*}"
socket_path="/tmp/.X11-unix/X$display_number"
lock_path="/tmp/.X$display_number-lock"

if ! DISPLAY="$DISPLAY_ID" XAUTHORITY= xdpyinfo >/dev/null 2>&1; then
  if [[ -S "$socket_path" ]] && ! pgrep -u "$USER" -f "Xvfb $DISPLAY_ID( |$)" >/dev/null 2>&1; then
    rm -f "$socket_path"
  fi
  if [[ -f "$lock_path" ]] && ! pgrep -u "$USER" -f "Xvfb $DISPLAY_ID( |$)" >/dev/null 2>&1; then
    rm -f "$lock_path"
  fi
  echo "Starting local Xvfb display $DISPLAY_ID with screen $SCREEN"
  env XAUTHORITY= setsid Xvfb "$DISPLAY_ID" -screen 0 "$SCREEN" -ac >"$LOG_DIR/xvfb.log" 2>&1 < /dev/null &
  sleep 2
fi

if ! DISPLAY="$DISPLAY_ID" XAUTHORITY= xdpyinfo >/dev/null 2>&1; then
  echo "Display $DISPLAY_ID is not reachable after Xvfb startup." >&2
  echo "Xvfb log:"
  tail -n 80 "$LOG_DIR/xvfb.log" 2>/dev/null || true
  exit 4
fi

if ! pgrep -u "$USER" -f "$LABVIEW_BIN" >/dev/null 2>&1; then
  echo "Starting LabVIEW Community on $DISPLAY_ID"
  env DISPLAY="$DISPLAY_ID" XAUTHORITY= setsid "$LABVIEW_BIN" >"$LOG_DIR/labview.log" 2>&1 < /dev/null &
  sleep 8
else
  echo "LabVIEW is already running for user $USER"
fi

echo
echo "Local LabVIEW display:"
DISPLAY="$DISPLAY_ID" XAUTHORITY= xdpyinfo | grep -E 'dimensions|depth of root window' || true

echo
echo "LabVIEW windows on $DISPLAY_ID:"
DISPLAY="$DISPLAY_ID" XAUTHORITY= xwininfo -root -tree | grep -E 'LabVIEW|Activation|Context Help' || true

echo
echo "Local LabVIEW ports:"
ss -ltnp | grep -E "(:$ACTIVATION_PORT|:$VI_SERVER_PORT|:$MCP_HTTP_PORT)" || true

echo
echo "Expected states:"
echo "  Activation callback: 127.0.0.1:$ACTIVATION_PORT while Community activation is pending"
echo "  VI Server:           127.0.0.1:$VI_SERVER_PORT after activation and VI Server startup"
echo "  LabVIEW MCP VI:      127.0.0.1:$MCP_HTTP_PORT after running nineman-YU/Labview_mcp/src/mcp_server_main.vi"
echo
echo "Logs:"
echo "  $LOG_DIR"
