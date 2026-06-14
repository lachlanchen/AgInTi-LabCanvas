#!/usr/bin/env bash
set -euo pipefail

PORT="${JLCPCB_CDP_PORT:-49237}"
PROFILE="${JLCPCB_CHROME_PROFILE:-$HOME/.cache/jlcpcb-order-shared}"
URL="${JLCPCB_START_URL:-https://www.jlc.com/newOrder/#/pcb/newOnlinePlaceOrder?spm=jlc-pc.newcenterpage.business}"

if curl -fsS "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
  echo "Chrome CDP already running on port ${PORT}"
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

"${CHROME}" \
  --remote-debugging-port="${PORT}" \
  --user-data-dir="${PROFILE}" \
  --no-first-run \
  --new-window "${URL}" >/tmp/jlcpcb-order-chrome.log 2>&1 &

echo "Launched ${CHROME} with CDP port ${PORT}"
echo "Profile: ${PROFILE}"
echo "Log: /tmp/jlcpcb-order-chrome.log"
