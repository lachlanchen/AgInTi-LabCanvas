#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DISPLAY_ID="${WECHAT_DISPLAY:-:97}"
VNC_PORT="${WECHAT_VNC_PORT:-5917}"
NOVNC_PORT="${WECHAT_NOVNC_PORT:-6107}"
LOG_DIR="$ROOT/output/virtual_desktop/$(date +%F)"

"$ROOT/agentic_tools/virtual_desktop/launch_virtual_desktop.sh" \
  --name wechat \
  --display "$DISPLAY_ID" \
  --screen 1920x1080x24 \
  --vnc-port "$VNC_PORT" \
  --novnc-port "$NOVNC_PORT" \
  --log-dir "$LOG_DIR" \
  -- /bin/true >/tmp/wechat_virtual_desktop_launch.log

if ! DISPLAY="$DISPLAY_ID" XAUTHORITY= xdotool search --onlyvisible --class wechat >/dev/null 2>&1; then
  DISPLAY="$DISPLAY_ID" XAUTHORITY= NO_AT_BRIDGE=1 setsid -f /usr/bin/wechat \
    >"$LOG_DIR/wechat_app.log" 2>&1
  sleep 5
fi

cat /tmp/wechat_virtual_desktop_launch.log
echo
echo "WeChat noVNC:"
echo "  http://127.0.0.1:${NOVNC_PORT}/vnc_lite.html?host=127.0.0.1&port=${NOVNC_PORT}&autoconnect=1&resize=remote"
