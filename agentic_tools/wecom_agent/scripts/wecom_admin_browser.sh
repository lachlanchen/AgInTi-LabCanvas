#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
DISPLAY_ID="${WECOM_ADMIN_DISPLAY:-:93}"
VNC_PORT="${WECOM_ADMIN_VNC_PORT:-5933}"
NOVNC_PORT="${WECOM_ADMIN_NOVNC_PORT:-6133}"
CDP_PORT="${WECOM_ADMIN_CDP_PORT:-9353}"
PROFILE="${WECOM_ADMIN_CHROME_PROFILE:-$HOME/.local/state/labcanvas-wecom-admin/chrome-profile}"
ADMIN_URL="${WECOM_ADMIN_URL:-https://work.weixin.qq.com/wework_admin/frame}"
NOVNC_URL="http://127.0.0.1:${NOVNC_PORT}/vnc.html?host=127.0.0.1&port=${NOVNC_PORT}&autoconnect=1&resize=scale"

"$ROOT/agentic_tools/virtual_desktop/launch_virtual_desktop.sh" \
  --name wecom-admin \
  --display "$DISPLAY_ID" \
  --vnc-port "$VNC_PORT" \
  --novnc-port "$NOVNC_PORT" >/tmp/labcanvas-wecom-admin-desktop.log

urlencode() {
  python3 - "$1" <<'PY'
import sys
from urllib.parse import quote
print(quote(sys.argv[1], safe=""))
PY
}

if curl -fsS "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; then
  existing_id="$(curl -fsS "http://127.0.0.1:${CDP_PORT}/json/list" | python3 -c '
import json, sys
for page in json.load(sys.stdin):
    if page.get("type") == "page" and "work.weixin.qq.com/wework_admin/" in page.get("url", ""):
        print(page.get("id", ""))
        break
')"
  if [[ -n "$existing_id" ]]; then
    curl -fsS "http://127.0.0.1:${CDP_PORT}/json/activate/${existing_id}" >/tmp/labcanvas-wecom-admin-tab.json
  else
    encoded="$(urlencode "$ADMIN_URL")"
    curl -fsS -X PUT "http://127.0.0.1:${CDP_PORT}/json/new?${encoded}" >/tmp/labcanvas-wecom-admin-tab.json
  fi
else
  if command -v google-chrome >/dev/null 2>&1; then
    CHROME=google-chrome
  elif command -v chromium >/dev/null 2>&1; then
    CHROME=chromium
  elif command -v chromium-browser >/dev/null 2>&1; then
    CHROME=chromium-browser
  else
    echo "Chrome/Chromium is not installed" >&2
    exit 3
  fi
  mkdir -p "$PROFILE"
  env DISPLAY="$DISPLAY_ID" XAUTHORITY= setsid "$CHROME" \
    --remote-debugging-address=127.0.0.1 \
    --remote-debugging-port="$CDP_PORT" \
    --user-data-dir="$PROFILE" \
    --no-first-run \
    --new-window "$ADMIN_URL" >/tmp/labcanvas-wecom-admin-chrome.log 2>&1 < /dev/null &
  for _ in $(seq 1 30); do
    curl -fsS "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1 && break
    sleep 0.5
  done
fi

fit_admin_window() {
  command -v xdotool >/dev/null 2>&1 || return 0
  local window_id=""
  local width="1920"
  local height="1080"
  for _ in $(seq 1 30); do
    window_id="$(env DISPLAY="$DISPLAY_ID" XAUTHORITY= xdotool search --onlyvisible --class 'google-chrome' 2>/dev/null | tail -n 1 || true)"
    [[ -n "$window_id" ]] && break
    sleep 0.2
  done
  [[ -n "$window_id" ]] || return 0
  read -r width height < <(env DISPLAY="$DISPLAY_ID" XAUTHORITY= xdotool getdisplaygeometry)
  env DISPLAY="$DISPLAY_ID" XAUTHORITY= xdotool \
    windowmap "$window_id" \
    windowmove --sync "$window_id" 0 0 \
    windowsize --sync "$window_id" "$width" "$height" \
    windowraise "$window_id" >/dev/null 2>&1 || true
}

fit_admin_window

echo "WeCom admin opened in its dedicated persistent browser profile."
echo "noVNC: $NOVNC_URL"
echo "CDP: http://127.0.0.1:${CDP_PORT}"
echo "Profile: $PROFILE"
