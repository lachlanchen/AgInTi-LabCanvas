#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
TEMPLATE="$ROOT/agentic_tools/wecom_agent/systemd/labcanvas-wecom-autostart.service.in"
UNIT_NAME="labcanvas-wecom-autostart.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_PATH="$UNIT_DIR/$UNIT_NAME"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
BUS="unix:path=$RUNTIME_DIR/bus"
ACTION="${1:-install}"

systemctl_user() {
  env DBUS_SESSION_BUS_ADDRESS="$BUS" systemctl --user "$@"
}

install_unit() {
  mkdir -p "$UNIT_DIR"
  python3 - "$TEMPLATE" "$UNIT_PATH" "$ROOT" "$HOME" <<'PY'
from pathlib import Path
import os
import sys

template, destination, root, home = map(Path, sys.argv[1:])
content = template.read_text(encoding="utf-8")
content = content.replace("@ROOT@", str(root)).replace("@HOME@", str(home))
temporary = destination.with_suffix(destination.suffix + ".tmp")
temporary.write_text(content, encoding="utf-8")
os.chmod(temporary, 0o644)
os.replace(temporary, destination)
PY
  systemctl_user daemon-reload
  systemctl_user enable --now "$UNIT_NAME"
  systemctl_user --no-pager --full status "$UNIT_NAME"
  loginctl show-user "$USER" -p Linger
}

case "$ACTION" in
  install)
    install_unit
    ;;
  start|stop|restart)
    systemctl_user "$ACTION" "$UNIT_NAME"
    ;;
  status)
    systemctl_user --no-pager --full status "$UNIT_NAME"
    ;;
  disable)
    systemctl_user disable --now "$UNIT_NAME"
    ;;
  *)
    echo "Usage: install_wecom_autostart.sh install|start|stop|restart|status|disable" >&2
    exit 2
    ;;
esac
