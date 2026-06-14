#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${JLCPCB_ORDER_CONFIG:-$HOME/.config/jlcpcb-order/private.json}"
SURFACE_FINISH="${JLCPCB_SURFACE_FINISH:-OSP}"
SHIPPING_MODE="${JLCPCB_SHIPPING_MODE:-separate}"
CONFIRM_MODE="${JLCPCB_CONFIRM_MODE:-manual}"
SCREENSHOT="${JLCPCB_SCREENSHOT:-/tmp/jlcpcb-assistant-handoff.png}"
ZIP_ARG="${1:-}"
ASSISTANT_BIN="${JLCPCB_ASSISTANT_BIN:-/opt/jlc-assistant/jlc-assistant}"

"$SCRIPT_DIR/launch_shared_chrome.sh"

prepare_cmd=(
  python3 "$SCRIPT_DIR/jlc_order_cdp.py"
  --config "$CONFIG"
  --screenshot "$SCREENSHOT"
  prepare
  --surface-finish "$SURFACE_FINISH"
  --shipping-mode "$SHIPPING_MODE"
  --order-channel assistant
  --confirm-mode "$CONFIRM_MODE"
)

if [[ -n "$ZIP_ARG" ]]; then
  prepare_cmd+=(--zip "$ZIP_ARG")
fi

"${prepare_cmd[@]}"

python3 "$SCRIPT_DIR/jlc_order_cdp.py" --config "$CONFIG" record-order \
  --status "assistant_handoff" \
  --note "Assistant channel selected after order check; continue manually in JLC desktop assistant."

if [[ -x "$ASSISTANT_BIN" ]]; then
  nohup "$ASSISTANT_BIN" >/tmp/jlcpcb-assistant.log 2>&1 &
  echo "Opened JLC assistant: $ASSISTANT_BIN"
else
  echo "JLC assistant binary not found or not executable at $ASSISTANT_BIN"
fi

echo "Assistant handoff prepared. Continue in the desktop assistant only after verifying the order preview."
