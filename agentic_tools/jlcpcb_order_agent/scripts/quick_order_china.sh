#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${JLCPCB_ORDER_CONFIG:-$HOME/.config/jlcpcb-order/private.json}"
SURFACE_FINISH="${JLCPCB_SURFACE_FINISH:-OSP}"
SHIPPING_MODE="${JLCPCB_SHIPPING_MODE:-separate}"
ORDER_CHANNEL="${JLCPCB_ORDER_CHANNEL:-web}"
CONFIRM_MODE="${JLCPCB_CONFIRM_MODE:-manual}"
ALLOW_SUBMIT="${JLCPCB_ALLOW_SUBMIT:-0}"
SCREENSHOT="${JLCPCB_SCREENSHOT:-/tmp/jlcpcb-china-quick.png}"
ZIP_ARG="${1:-}"

"$SCRIPT_DIR/launch_shared_chrome.sh"

prepare_cmd=(
  python3 "$SCRIPT_DIR/jlc_order_cdp.py"
  --config "$CONFIG"
  --screenshot "$SCREENSHOT"
  prepare
  --surface-finish "$SURFACE_FINISH"
  --shipping-mode "$SHIPPING_MODE"
  --order-channel "$ORDER_CHANNEL"
  --confirm-mode "$CONFIRM_MODE"
)

if [[ -n "$ZIP_ARG" ]]; then
  prepare_cmd+=(--zip "$ZIP_ARG")
fi

"${prepare_cmd[@]}"

python3 "$SCRIPT_DIR/jlc_order_cdp.py" --config "$CONFIG" record-order \
  --status "china_checked" \
  --note "Quick China flow checked order; channel=$ORDER_CHANNEL finish=$SURFACE_FINISH shipping=$SHIPPING_MODE."

if [[ "$ALLOW_SUBMIT" == "1" ]]; then
  python3 "$SCRIPT_DIR/jlc_order_cdp.py" --config "$CONFIG" --screenshot "$SCREENSHOT" submit --allow-submit
  python3 "$SCRIPT_DIR/jlc_order_cdp.py" --config "$CONFIG" record-order \
    --status "submitted_pending_review" \
    --note "Quick China flow submitted after explicit JLCPCB_ALLOW_SUBMIT=1."
else
  echo "Prepared and checked. Final submit was not run; set JLCPCB_ALLOW_SUBMIT=1 only after manual review."
fi
