#!/usr/bin/env bash
set -euo pipefail

PORT="${LABVIEW_VI_SERVER_PORT:-3363}"
PREF_DIR="${LABVIEW_PREF_DIR:-$HOME/natinst/.config/LabVIEW-2026}"
PREF_FILE="${LABVIEW_PREF_FILE:-$PREF_DIR/labview.conf}"

mkdir -p "$PREF_DIR"

udc_install_id=""
if [[ -f "$PREF_FILE" ]]; then
  udc_install_id="$(grep -E '^UDCInstallID=' "$PREF_FILE" | tail -n 1 || true)"
  cp -a "$PREF_FILE" "$PREF_FILE.bak.$(date +%Y%m%d_%H%M%S)"
fi

tmp_file="$(mktemp)"
cat >"$tmp_file" <<EOF
[LabVIEW]
server.tcp.enabled=True
server.tcp.port=$PORT
server.tcp.paranoid=True
server.tcp.access="+127.0.0.1"
server.vi.access="+*"
server.vi.callsEnabled=True
server.vi.propertiesEnabled=True
server.app.propertiesEnabled=True

# Compatibility resource names observed in the LabVIEW 2026 binary.
labview.server.tcp.enabled=True
labview.server.tcp.port=$PORT
labview.server.tcp.paranoid=True
labview.server.tcp.access="+127.0.0.1"
labview.server.vi.access="+*"
labview.server.vi.callsEnabled=True
labview.server.vi.propertiesEnabled=True
labview.server.app.propertiesEnabled=True
EOF

if [[ -n "$udc_install_id" ]]; then
  printf '%s\n' "$udc_install_id" >>"$tmp_file"
fi

mv "$tmp_file" "$PREF_FILE"
chmod 600 "$PREF_FILE"

echo "Configured LabVIEW VI Server preferences:"
echo "  $PREF_FILE"
echo "  VI Server TCP port: $PORT"
