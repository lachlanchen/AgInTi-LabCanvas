#!/usr/bin/env bash
set -euo pipefail

VERSION="${LCEDA_PRO_VERSION:-3.2.149}"
ARCHIVE="${1:-$HOME/Downloads/lceda-pro-linux-x64-${VERSION}.zip}"
INSTALL_ROOT="${LCEDA_PRO_INSTALL_ROOT:-$HOME/.local/opt/lceda-pro-${VERSION}}"
WRAPPER="${LCEDA_PRO_WRAPPER:-$HOME/.local/bin/lceda-pro}"
TMP_ROOT="${INSTALL_ROOT}.tmp.$$"

if [[ ! -f "$ARCHIVE" ]]; then
  echo "Archive not found: $ARCHIVE" >&2
  exit 1
fi

if pgrep -f "$INSTALL_ROOT/lceda-pro/lceda-pro" >/dev/null 2>&1; then
  echo "LCEDA Pro appears to be running from $INSTALL_ROOT; close it before reinstalling." >&2
  exit 1
fi

unzip -tq "$ARCHIVE" >/dev/null
rm -rf "$TMP_ROOT"
mkdir -p "$TMP_ROOT"
unzip -q "$ARCHIVE" -d "$TMP_ROOT"

if [[ ! -x "$TMP_ROOT/lceda-pro/lceda-pro" ]]; then
  echo "Unexpected archive layout; expected lceda-pro/lceda-pro" >&2
  rm -rf "$TMP_ROOT"
  exit 1
fi

rm -rf "$INSTALL_ROOT"
mv "$TMP_ROOT" "$INSTALL_ROOT"
chmod +x "$INSTALL_ROOT/lceda-pro/lceda-pro" \
  "$INSTALL_ROOT/lceda-pro/chrome-sandbox" \
  "$INSTALL_ROOT/lceda-pro/chrome_crashpad_handler" 2>/dev/null || true

mkdir -p "$(dirname "$WRAPPER")"
cat > "$WRAPPER" <<'WRAP'
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${LCEDA_PRO_HOME:-$HOME/.local/opt/lceda-pro-3.2.149/lceda-pro}"
ARGS=()

if [[ "${LCEDA_PRO_NO_SANDBOX:-1}" == "1" ]]; then
  ARGS+=(--no-sandbox)
fi

if [[ -n "${LCEDA_PRO_EXTRA_ARGS:-}" ]]; then
  read -r -a EXTRA_ARGS <<< "$LCEDA_PRO_EXTRA_ARGS"
  ARGS+=("${EXTRA_ARGS[@]}")
fi

exec "$APP_DIR/lceda-pro" "${ARGS[@]}" "$@"
WRAP
chmod +x "$WRAPPER"

echo "Installed LCEDA Pro to $INSTALL_ROOT"
echo "Wrapper: $WRAPPER"
