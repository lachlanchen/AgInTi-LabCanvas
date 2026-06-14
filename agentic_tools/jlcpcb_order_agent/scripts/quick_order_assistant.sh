#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${JLCPCB_ORDER_CONFIG:-$HOME/.config/jlcpcb-order/private.json}"
SURFACE_FINISH="${JLCPCB_SURFACE_FINISH:-OSP}"
SHIPPING_MODE="${JLCPCB_SHIPPING_MODE:-separate}"
CONFIRM_MODE="${JLCPCB_CONFIRM_MODE:-manual}"
SCREENSHOT="${JLCPCB_SCREENSHOT:-/tmp/jlcpcb-assistant-handoff.png}"
ZIP_ARG="${1:-}"
ASSISTANT_LOG="${JLCPCB_ASSISTANT_LOG:-$HOME/.cache/jlcpcb-order/assistant/assistant.log}"

LOCAL_ASSISTANT="${HOME}/.local/bin/jlc-assistant"
SYSTEM_ASSISTANT="/opt/jlc-assistant/jlc-assistant"
ASSISTANT_BIN="${JLCPCB_ASSISTANT_BIN:-$LOCAL_ASSISTANT}"

if [[ ! -x "$ASSISTANT_BIN" && -x "$SYSTEM_ASSISTANT" ]]; then
  ASSISTANT_BIN="$SYSTEM_ASSISTANT"
fi

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
  JLCPCB_ASSISTANT_BIN="$ASSISTANT_BIN" \
  JLCPCB_ASSISTANT_LOG="$ASSISTANT_LOG" \
    "$SCRIPT_DIR/launch_assistant_local.sh"
else
  echo "JLC assistant binary not found or not executable at $ASSISTANT_BIN"
fi

echo "Assistant handoff prepared. Continue in the desktop assistant only after verifying the order preview."
