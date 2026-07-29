#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

if [[ -n "${JLCPCB_TAB_CDP_PORT:-}" ]]; then
  echo "JLCPCB_TAB_CDP_PORT is no longer supported." >&2
  echo "JLC must use its dedicated browser; the AgInTi Browser/XYQ profile is left untouched." >&2
  exit 2
fi

exec "$SCRIPT_DIR/jlc_browser_stack.sh" start "$@"
