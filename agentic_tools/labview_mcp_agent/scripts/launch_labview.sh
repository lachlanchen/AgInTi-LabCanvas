#!/usr/bin/env bash
set -euo pipefail

USE_XVFB="${LABVIEW_USE_XVFB:-0}"
DISPLAY_ID="${LABVIEW_DISPLAY:-:99}"
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
  if ! pgrep -f "Xvfb $DISPLAY_ID" >/dev/null 2>&1; then
    Xvfb "$DISPLAY_ID" -screen 0 1920x1080x24 >/tmp/labview-xvfb.log 2>&1 &
    sleep 1
  fi
  export DISPLAY="$DISPLAY_ID"
fi

exec "$LABVIEW_BIN" "$@"
