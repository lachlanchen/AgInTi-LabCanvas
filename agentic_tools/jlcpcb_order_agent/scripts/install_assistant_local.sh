#!/usr/bin/env bash
set -euo pipefail

VERSION="${JLC_ASSISTANT_VERSION:-5.0.69}"
ZIP_PATH="${1:-${JLC_ASSISTANT_ZIP:-$HOME/Downloads/JLCPcAssit-linux-x64-$VERSION.zip}}"
INSTALL_ROOT="${JLC_ASSISTANT_INSTALL_ROOT:-$HOME/.local/opt}"
INSTALL_DIR="$INSTALL_ROOT/jlc-assistant-$VERSION"
APP_DIR="$INSTALL_DIR/jlc-assistant"
WRAPPER="${JLC_ASSISTANT_WRAPPER:-$HOME/.local/bin/jlc-assistant}"

if [[ ! -f "$ZIP_PATH" ]]; then
  echo "missing JLC assistant ZIP: $ZIP_PATH" >&2
  exit 1
fi

if ! command -v unzip >/dev/null 2>&1; then
  echo "unzip is required" >&2
  exit 1
fi

if [[ "${JLC_ASSISTANT_REINSTALL:-0}" == "1" ]]; then
  rm -rf "$INSTALL_DIR"
fi

mkdir -p "$INSTALL_DIR" "$(dirname "$WRAPPER")"

if [[ ! -x "$APP_DIR/jlc-assistant" ]]; then
  unzip -q "$ZIP_PATH" -d "$INSTALL_DIR"
fi

chmod +x "$APP_DIR/jlc-assistant"
if [[ -f "$APP_DIR/chrome_crashpad_handler" ]]; then
  chmod +x "$APP_DIR/chrome_crashpad_handler"
fi

cat >"$WRAPPER" <<EOF
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="\${JLC_ASSISTANT_HOME:-$APP_DIR}"
ARGS=()

if [[ "\${JLC_ASSISTANT_NO_SANDBOX:-0}" == "1" ]]; then
  ARGS+=(--no-sandbox)
fi

if [[ -n "\${JLC_ASSISTANT_EXTRA_ARGS:-}" ]]; then
  read -r -a EXTRA_ARGS <<< "\$JLC_ASSISTANT_EXTRA_ARGS"
  ARGS+=("\${EXTRA_ARGS[@]}")
fi

exec "\$APP_DIR/jlc-assistant" "\${ARGS[@]}" "\$@"
EOF

chmod +x "$WRAPPER"

echo "Installed JLC assistant locally:"
echo "  app:     $APP_DIR/jlc-assistant"
echo "  wrapper: $WRAPPER"

if [[ -f "$APP_DIR/chrome-sandbox" ]]; then
  if [[ "$(stat -c '%U:%G %a' "$APP_DIR/chrome-sandbox" 2>/dev/null || true)" != "root:root 4755" ]]; then
    echo
    echo "Optional sandbox setup, if your desktop allows it:"
    echo "  sudo chown root:root '$APP_DIR/chrome-sandbox'"
    echo "  sudo chmod 4755 '$APP_DIR/chrome-sandbox'"
  fi
fi

echo
echo "Run:"
echo "  $WRAPPER"
echo
echo "Remote desktops that block the Electron sandbox can use:"
echo "  JLC_ASSISTANT_NO_SANDBOX=1 JLC_ASSISTANT_EXTRA_ARGS='--disable-gpu' $WRAPPER"
