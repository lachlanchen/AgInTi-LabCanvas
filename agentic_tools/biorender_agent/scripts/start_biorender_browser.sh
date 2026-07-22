#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
LAUNCHER="$ROOT/agentic_tools/virtual_desktop/launch_virtual_desktop.sh"
DISPLAY_ID="${BIORENDER_DISPLAY:-:89}"
VNC_PORT="${BIORENDER_VNC_PORT:-5989}"
NOVNC_PORT="${BIORENDER_NOVNC_PORT:-6189}"
CDP_PORT="${BIORENDER_CDP_PORT:-9389}"
PROFILE="${BIORENDER_CHROME_PROFILE:-$HOME/.local/share/labcanvas/biorender/chrome-profile}"
LOG_DIR="${BIORENDER_LOG_DIR:-$ROOT/output/virtual_desktop/biorender}"
START_URL="${1:-https://app.biorender.com/user/signin}"

mkdir -p "$PROFILE" "$LOG_DIR"

desktop_args=(
  --name biorender
  --display "$DISPLAY_ID"
  --screen 1920x1080x24
  --vnc-port "$VNC_PORT"
  --novnc-port "$NOVNC_PORT"
  --log-dir "$LOG_DIR"
)

if curl -fsS --max-time 2 "http://127.0.0.1:$CDP_PORT/json/version" >/dev/null 2>&1; then
  "$LAUNCHER" "${desktop_args[@]}"
else
  "$LAUNCHER" "${desktop_args[@]}" -- \
    /opt/google/chrome/chrome \
      --remote-debugging-address=127.0.0.1 \
      --remote-debugging-port="$CDP_PORT" \
      --remote-allow-origins="http://127.0.0.1:$CDP_PORT" \
      --user-data-dir="$PROFILE" \
      --no-first-run \
      --no-default-browser-check \
      --disable-dev-shm-usage \
      --ozone-platform=x11 \
      --window-position=0,0 \
      --window-size=1920,1080 \
      "$START_URL"
fi

echo "BioRender noVNC: http://127.0.0.1:$NOVNC_PORT/vnc.html?host=127.0.0.1&port=$NOVNC_PORT&autoconnect=1&resize=scale"
echo "BioRender CDP:   http://127.0.0.1:$CDP_PORT"
