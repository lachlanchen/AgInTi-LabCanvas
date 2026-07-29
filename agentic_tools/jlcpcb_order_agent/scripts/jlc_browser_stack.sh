#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd -P)"
VIRTUAL_DESKTOP="$ROOT/agentic_tools/virtual_desktop/launch_virtual_desktop.sh"

DISPLAY_ID="${JLCPCB_DISPLAY:-:104}"
SCREEN="${JLCPCB_SCREEN:-1920x1080x24}"
VNC_PORT="${JLCPCB_VNC_PORT:-5924}"
NOVNC_PORT="${JLCPCB_NOVNC_PORT:-6124}"
CDP_PORT="${JLCPCB_CDP_PORT:-49237}"
PROFILE="${JLCPCB_CHROME_PROFILE:-$HOME/.cache/jlcpcb-order-shared}"
START_URL="${JLCPCB_START_URL:-https://www.jlc.com/newOrder/#/pcb/newOnlinePlaceOrder?spm=jlc-pc.newcenterpage.business}"
STATE_DIR="${JLCPCB_BROWSER_STATE_DIR:-$HOME/.local/state/jlcpcb-order/browser}"
LOG_DIR="$STATE_DIR/logs"
USER_NAME="${USER:-$(id -un)}"

NOVNC_URL="http://127.0.0.1:${NOVNC_PORT}/vnc.html?host=127.0.0.1&port=${NOVNC_PORT}&autoconnect=1&resize=scale"

usage() {
  cat <<'EOF'
Usage:
  jlc_browser_stack.sh start
  jlc_browser_stack.sh status [--json]
  jlc_browser_stack.sh config [--json]
  jlc_browser_stack.sh url
  jlc_browser_stack.sh stop

The JLC browser has its own X display, VNC/noVNC ports, CDP port, and persistent
Chrome profile. It never opens a tab in the AgInTi Browser/Xiaoyunque profile.
Calling start repeatedly reuses the current JLC process and existing JLC tab.
EOF
}

find_chrome() {
  if command -v google-chrome >/dev/null 2>&1; then
    command -v google-chrome
  elif command -v chromium >/dev/null 2>&1; then
    command -v chromium
  elif command -v chromium-browser >/dev/null 2>&1; then
    command -v chromium-browser
  else
    return 1
  fi
}

cdp_ready() {
  curl -fsS --max-time 2 "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1
}

display_ready() {
  timeout 2s env DISPLAY="$DISPLAY_ID" XAUTHORITY= xdpyinfo >/dev/null 2>&1
}

port_listening() {
  local port="$1"
  ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${port}$"
}

profile_processes() {
  pgrep -u "$USER_NAME" -af -- "--user-data-dir=${PROFILE}" 2>/dev/null || true
}

expected_vnc_running() {
  pgrep -u "$USER_NAME" -af x11vnc 2>/dev/null \
    | grep -F -- "-display ${DISPLAY_ID}" \
    | grep -Eq -- "-rfbport ${VNC_PORT}( |$)"
}

expected_novnc_running() {
  pgrep -u "$USER_NAME" -af websockify 2>/dev/null \
    | grep -F -- "127.0.0.1:${NOVNC_PORT} 127.0.0.1:${VNC_PORT}"
}

fail_on_foreign_listener() {
  local port="$1"
  local expected="$2"
  local label="$3"
  if port_listening "$port" && ! "$expected"; then
    echo "Refusing to reuse ${label} port ${port}; another service is listening." >&2
    exit 4
  fi
}

has_jlc_tab() {
  python3 - "$CDP_PORT" <<'PY'
import json
import sys
from urllib.request import urlopen

port = int(sys.argv[1])
with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=3) as response:
    pages = json.load(response)
raise SystemExit(
    0
    if any(
        "jlc.com" in str(page.get("url", "")).lower()
        or "jlcpcb.com" in str(page.get("url", "")).lower()
        for page in pages
    )
    else 1
)
PY
}

open_jlc_tab_if_missing() {
  if has_jlc_tab; then
    return
  fi
  python3 - "$CDP_PORT" "$START_URL" <<'PY'
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen

port = int(sys.argv[1])
url = quote(sys.argv[2], safe="")
request = Request(f"http://127.0.0.1:{port}/json/new?{url}", method="PUT")
with urlopen(request, timeout=5):
    pass
PY
}

print_config_json() {
  python3 - "$DISPLAY_ID" "$SCREEN" "$VNC_PORT" "$NOVNC_PORT" "$CDP_PORT" "$PROFILE" "$NOVNC_URL" <<'PY'
import json
import sys

keys = ("display", "screen", "vnc_port", "novnc_port", "cdp_port", "profile", "novnc_url")
values = list(sys.argv[1:])
values[2:5] = [int(value) for value in values[2:5]]
print(json.dumps(dict(zip(keys, values)), ensure_ascii=False, sort_keys=True))
PY
}

print_status_json() {
  local display_ok=false
  local vnc_ok=false
  local novnc_ok=false
  local cdp_ok=false
  local profile_ok=false
  display_ready && display_ok=true
  expected_vnc_running && port_listening "$VNC_PORT" && vnc_ok=true
  expected_novnc_running && port_listening "$NOVNC_PORT" && novnc_ok=true
  cdp_ready && cdp_ok=true
  [[ -n "$(profile_processes)" ]] && profile_ok=true
  python3 - "$display_ok" "$vnc_ok" "$novnc_ok" "$cdp_ok" "$profile_ok" "$DISPLAY_ID" "$VNC_PORT" "$NOVNC_PORT" "$CDP_PORT" "$PROFILE" "$NOVNC_URL" <<'PY'
import json
import sys

display_ok, vnc_ok, novnc_ok, cdp_ok, profile_ok = (
    value == "true" for value in sys.argv[1:6]
)
payload = {
    "ready": all((display_ok, vnc_ok, novnc_ok, cdp_ok, profile_ok)),
    "display_ready": display_ok,
    "vnc_ready": vnc_ok,
    "novnc_ready": novnc_ok,
    "cdp_ready": cdp_ok,
    "profile_process_ready": profile_ok,
    "display": sys.argv[6],
    "vnc_port": int(sys.argv[7]),
    "novnc_port": int(sys.argv[8]),
    "cdp_port": int(sys.argv[9]),
    "profile": sys.argv[10],
    "novnc_url": sys.argv[11],
}
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
PY
}

start_stack() {
  if cdp_ready; then
    open_jlc_tab_if_missing
    echo "Reusing dedicated JLC browser."
    echo "CDP: http://127.0.0.1:${CDP_PORT}"
    echo "noVNC: ${NOVNC_URL}"
    return
  fi

  if [[ -n "$(profile_processes)" ]]; then
    echo "The JLC profile is already open but its expected CDP port is unavailable." >&2
    echo "Refusing to launch a second Chrome process against ${PROFILE}." >&2
    exit 3
  fi

  if port_listening "$CDP_PORT"; then
    echo "Refusing to use CDP port ${CDP_PORT}; another service is listening." >&2
    exit 4
  fi
  fail_on_foreign_listener "$VNC_PORT" expected_vnc_running "VNC"
  fail_on_foreign_listener "$NOVNC_PORT" expected_novnc_running "noVNC"

  local chrome
  chrome="$(find_chrome)" || {
    echo "No Chrome/Chromium binary found." >&2
    exit 3
  }

  mkdir -p "$PROFILE" "$LOG_DIR"
  chmod 700 "$PROFILE" "$STATE_DIR" 2>/dev/null || true

  "$VIRTUAL_DESKTOP" \
    --name jlcpcb-order \
    --display "$DISPLAY_ID" \
    --screen "$SCREEN" \
    --vnc-port "$VNC_PORT" \
    --novnc-port "$NOVNC_PORT" \
    --log-dir "$LOG_DIR" \
    --app-match "$PROFILE" \
    -- "$chrome" \
      "--remote-debugging-address=127.0.0.1" \
      "--remote-debugging-port=${CDP_PORT}" \
      "--remote-allow-origins=http://127.0.0.1:${CDP_PORT}" \
      "--user-data-dir=${PROFILE}" \
      --no-first-run \
      --no-default-browser-check \
      --disable-default-apps \
      --disable-sync \
      --disable-session-crashed-bubble \
      --start-maximized \
      "$START_URL"

  for _ in $(seq 1 40); do
    cdp_ready && break
    sleep 0.5
  done
  if ! cdp_ready; then
    echo "JLC Chrome did not expose CDP on ${CDP_PORT}; inspect ${LOG_DIR}." >&2
    exit 5
  fi

  open_jlc_tab_if_missing
  echo "Dedicated JLC browser ready."
  echo "CDP: http://127.0.0.1:${CDP_PORT}"
  echo "noVNC: ${NOVNC_URL}"
}

stop_stack() {
  pkill -TERM -u "$USER_NAME" -f -- "--user-data-dir=${PROFILE}" 2>/dev/null || true
  pgrep -u "$USER_NAME" -af websockify 2>/dev/null \
    | grep -F -- "127.0.0.1:${NOVNC_PORT} 127.0.0.1:${VNC_PORT}" \
    | awk '{print $1}' \
    | xargs -r kill -TERM
  pgrep -u "$USER_NAME" -af x11vnc 2>/dev/null \
    | grep -F -- "-display ${DISPLAY_ID}" \
    | grep -Eq -- "-rfbport ${VNC_PORT}( |$)" \
    && pgrep -u "$USER_NAME" -af x11vnc 2>/dev/null \
      | grep -F -- "-display ${DISPLAY_ID}" \
      | grep -E -- "-rfbport ${VNC_PORT}( |$)" \
      | awk '{print $1}' \
      | xargs -r kill -TERM \
    || true
  pkill -TERM -u "$USER_NAME" -f "Xvfb ${DISPLAY_ID}( |$)" 2>/dev/null || true
  echo "Stopped only the dedicated JLC browser stack."
}

command_name="${1:-start}"
shift || true
json_output=false
if [[ "${1:-}" == "--json" ]]; then
  json_output=true
  shift
fi
if [[ $# -gt 0 ]]; then
  usage >&2
  exit 2
fi

case "$command_name" in
  start)
    start_stack
    ;;
  status)
    if "$json_output"; then
      print_status_json
    else
      print_status_json | python3 -m json.tool
    fi
    ;;
  config)
    if "$json_output"; then
      print_config_json
    else
      print_config_json | python3 -m json.tool
    fi
    ;;
  url)
    echo "$NOVNC_URL"
    ;;
  stop)
    stop_stack
    ;;
  --help|-h|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
