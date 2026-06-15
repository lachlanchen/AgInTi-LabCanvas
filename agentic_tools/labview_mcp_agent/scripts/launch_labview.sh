#!/usr/bin/env bash
set -euo pipefail

USE_XVFB="${LABVIEW_USE_XVFB:-0}"
DISPLAY_ID="${LABVIEW_DISPLAY:-:99}"
XVFB_SCREEN="${LABVIEW_XVFB_SCREEN:-1920x1080x24}"
LABVIEW_BIN="${LABVIEW_BIN:-}"

if [[ -z "$LABVIEW_BIN" ]]; then
  for candidate in labview64 labview /usr/local/natinst/LabVIEW-2026-64/labview; do
    if command -v "$candidate" >/dev/null 2>&1 || [[ -x "$candidate" ]]; then
      LABVIEW_BIN="$candidate"
      break
    fi
  done
fi

if [[ -z "$LABVIEW_BIN" ]] || { ! command -v "$LABVIEW_BIN" >/dev/null 2>&1 && [[ ! -x "$LABVIEW_BIN" ]]; }; then
  echo "LabVIEW launcher not found: ${LABVIEW_BIN:-<auto>}" >&2
  echo "Install LabVIEW first or set LABVIEW_BIN=/path/to/labview." >&2
  exit 3
fi

if [[ "$USE_XVFB" == 1 ]]; then
  if ! command -v Xvfb >/dev/null 2>&1; then
    echo "Xvfb is missing; install xvfb or launch with LABVIEW_USE_XVFB=0." >&2
    exit 4
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
    env XAUTHORITY= setsid Xvfb "$DISPLAY_ID" -screen 0 "$XVFB_SCREEN" -ac >/tmp/labview-xvfb.log 2>&1 < /dev/null &
    sleep 1
  fi
  export DISPLAY="$DISPLAY_ID"
  unset XAUTHORITY
fi

exec "$LABVIEW_BIN" "$@"
