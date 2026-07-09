#!/usr/bin/env bash
set -euo pipefail

PORT="${JLCPCB_CDP_PORT:-49237}"
PROFILE="${JLCPCB_CHROME_PROFILE:-$HOME/.cache/jlcpcb-order-shared}"
URL="${JLCPCB_START_URL:-https://www.jlc.com/newOrder/#/pcb/newOnlinePlaceOrder?spm=jlc-pc.newcenterpage.business}"
TARGET_TAB_CDP_PORT="${JLCPCB_TAB_CDP_PORT:-}"
WINDOW_MODE="${JLCPCB_WINDOW_MODE:-window}"

case "${WINDOW_MODE}" in
  window|tab) ;;
  *)
    echo "JLCPCB_WINDOW_MODE must be 'window' or 'tab', got '${WINDOW_MODE}'" >&2
    exit 1
    ;;
esac

urlencode() {
  python3 - "$1" <<'PY'
import sys
from urllib.parse import quote

print(quote(sys.argv[1], safe=""))
PY
}

open_cdp_tab() {
  local target_port="$1"
  local target_url="$2"
  local encoded
  encoded="$(urlencode "${target_url}")"
  if ! curl -fsS "http://127.0.0.1:${target_port}/json/version" >/dev/null 2>&1; then
    echo "Target Chrome CDP is not running on port ${target_port}" >&2
    return 1
  fi
  curl -fsS -X PUT "http://127.0.0.1:${target_port}/json/new?${encoded}" >/tmp/jlcpcb-order-last-tab.json
  echo "Opened JLC page as a tab in Chrome CDP port ${target_port}"
  echo "Tab metadata: /tmp/jlcpcb-order-last-tab.json"
}

if [[ -n "${TARGET_TAB_CDP_PORT}" ]]; then
  open_cdp_tab "${TARGET_TAB_CDP_PORT}" "${URL}"
  exit 0
fi

if curl -fsS "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
  if [[ "${JLCPCB_OPEN_URL_ON_EXISTING:-1}" == "1" ]]; then
    open_cdp_tab "${PORT}" "${URL}"
  else
    echo "Chrome CDP already running on port ${PORT}"
  fi
  exit 0
fi

mkdir -p "${PROFILE}"

if command -v google-chrome >/dev/null 2>&1; then
  CHROME=google-chrome
elif command -v chromium >/dev/null 2>&1; then
  CHROME=chromium
elif command -v chromium-browser >/dev/null 2>&1; then
  CHROME=chromium-browser
else
  echo "No Chrome/Chromium binary found" >&2
  exit 1
fi

if command -v setsid >/dev/null 2>&1; then
  setsid "${CHROME}" \
    --remote-debugging-port="${PORT}" \
    --user-data-dir="${PROFILE}" \
    --no-first-run \
    "--new-${WINDOW_MODE}" "${URL}" >/tmp/jlcpcb-order-chrome.log 2>&1 < /dev/null &
else
  nohup "${CHROME}" \
    --remote-debugging-port="${PORT}" \
    --user-data-dir="${PROFILE}" \
    --no-first-run \
    "--new-${WINDOW_MODE}" "${URL}" >/tmp/jlcpcb-order-chrome.log 2>&1 < /dev/null &
fi

sleep 1
if ! curl -fsS "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
  echo "Chrome launch did not expose CDP on port ${PORT}; see /tmp/jlcpcb-order-chrome.log" >&2
  exit 1
fi

echo "Launched ${CHROME} with CDP port ${PORT}"
echo "Profile: ${PROFILE}"
echo "Log: /tmp/jlcpcb-order-chrome.log"
