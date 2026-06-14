#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${JLCPCB_ORDER_CONFIG:-$HOME/.config/jlcpcb-order/private.json}"
GLOBAL_URL="${JLCPCB_GLOBAL_URL:-https://cart.jlcpcb.com/quote?spm=jlcpcb.Public.2006}"
SCREENSHOT="${JLCPCB_SCREENSHOT:-/tmp/jlcpcb-global-quick.png}"
DOM_DIR="${JLCPCB_DOM_DIR:-$HOME/.config/jlcpcb-order/dom}"
ZIP_ARG="${1:-}"
ALLOW_SUBMIT="${JLCPCB_ALLOW_SUBMIT:-0}"

mkdir -p "$DOM_DIR"
"$SCRIPT_DIR/launch_shared_chrome.sh"

if [[ -n "$ZIP_ARG" ]]; then
  python3 "$SCRIPT_DIR/jlc_order_cdp.py" --config "$CONFIG" --screenshot "$SCREENSHOT" \
    global-upload --url "$GLOBAL_URL" --zip "$ZIP_ARG"
else
  python3 "$SCRIPT_DIR/jlc_order_cdp.py" --config "$CONFIG" --screenshot "$SCREENSHOT" \
    open-site --site global --url "$GLOBAL_URL"
fi

python3 "$SCRIPT_DIR/jlc_order_cdp.py" --config "$CONFIG" \
  dump-dom --url-contains "cart.jlcpcb.com" --output "$DOM_DIR/global-quote-latest.json"

if [[ "$ALLOW_SUBMIT" == "1" ]]; then
  python3 "$SCRIPT_DIR/jlc_order_cdp.py" --config "$CONFIG" --screenshot "$SCREENSHOT" \
    global-submit-current-cart --allow-submit
else
  echo "Global JLCPCB page opened and DOM snapshot saved. Set JLCPCB_ALLOW_SUBMIT=1 only after the cart item is correct."
fi
