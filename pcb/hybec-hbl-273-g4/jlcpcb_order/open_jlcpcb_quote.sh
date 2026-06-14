#!/usr/bin/env bash
set -euo pipefail

ORDER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZIP_FILE="$ORDER_DIR/hybec-hbl-273-g4-jlcpcb-gerber.zip"

if [[ ! -f "$ZIP_FILE" ]]; then
  echo "Missing $ZIP_FILE" >&2
  exit 1
fi

echo "Upload this file to JLCPCB:"
echo "$ZIP_FILE"
echo
echo "Recommended: open README.md in this folder while ordering."

if command -v xclip >/dev/null 2>&1; then
  printf '%s' "$ZIP_FILE" | xclip -selection clipboard
  echo "Copied file path to clipboard with xclip."
elif command -v wl-copy >/dev/null 2>&1; then
  printf '%s' "$ZIP_FILE" | wl-copy
  echo "Copied file path to clipboard with wl-copy."
fi

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "https://jlcpcb.com/quote" >/dev/null 2>&1 || true
fi
