#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

python3 "${SCRIPT_DIR}/wenext_order_cdp.py" \
  --site global \
  --config "${WENEXT_ORDER_CONFIG:-$HOME/.config/wenext-3d-order/private.json}" \
  "$@"
