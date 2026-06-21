#!/usr/bin/env bash
set -euo pipefail

DISPLAY_ID="${DISPLAY:-:98}"
INTERVAL="${VIRTUAL_DESKTOP_KEEP_AWAKE_INTERVAL:-55}"
ONCE="0"

usage() {
  cat <<'EOF'
Usage:
  keep_awake.sh [--display :N] [--interval SECONDS] [--once]

Disables X11 screensaver blanking and DPMS for an isolated virtual desktop.
The loop only calls xset; it does not move the mouse, press keys, or touch app
state.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --display) DISPLAY_ID="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --once) ONCE="1"; shift ;;
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

apply_keep_awake() {
  DISPLAY="$DISPLAY_ID" XAUTHORITY= xset s off
  DISPLAY="$DISPLAY_ID" XAUTHORITY= xset s noblank
  if DISPLAY="$DISPLAY_ID" XAUTHORITY= xset q 2>/dev/null | grep -q "DPMS is"; then
    DISPLAY="$DISPLAY_ID" XAUTHORITY= xset -dpms
  fi
  DISPLAY="$DISPLAY_ID" XAUTHORITY= xset s reset
}

need xset
apply_keep_awake

if [[ "$ONCE" == "1" ]]; then
  echo "Keep-awake applied on $DISPLAY_ID"
  exit 0
fi

echo "Keep-awake loop active on $DISPLAY_ID every ${INTERVAL}s"
while true; do
  sleep "$INTERVAL"
  apply_keep_awake || true
done
