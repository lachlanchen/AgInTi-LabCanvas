#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
ACTION="${1:-status}"
JSON=0
if [[ "${2:-}" == "--json" || "${1:-}" == "--json" ]]; then
  JSON=1
  [[ "$ACTION" == "--json" ]] && ACTION="status"
fi

PRIVATE="${WECOM_CLIENT_PRIVATE_DIR:-$ROOT/agentic_tools/wecom_agent/.private}"
PREFIX="${WECOM_CLIENT_WINEPREFIX:-$PRIVATE/wineprefix}"
INSTALLER="${WECOM_CLIENT_INSTALLER:-$PRIVATE/WeCom_windows_official.exe}"
DISPLAY_ID="${WECOM_CLIENT_DISPLAY:-:92}"
VNC_PORT="${WECOM_CLIENT_VNC_PORT:-5992}"
NOVNC_PORT="${WECOM_CLIENT_NOVNC_PORT:-6192}"
LOG_DIR="${WECOM_CLIENT_LOG_DIR:-$ROOT/output/virtual_desktop/wecom-client}"
DOWNLOAD_URL="${WECOM_CLIENT_DOWNLOAD_URL:-https://work.weixin.qq.com/wework_admin/commdownload?platform=win&from=wwindex}"
EXE_UNIX="$PREFIX/drive_c/Program Files (x86)/WXWork/WXWork.exe"
EXE_WINDOWS='C:\Program Files (x86)\WXWork\WXWork.exe'
NOVNC_URL="http://127.0.0.1:${NOVNC_PORT}/vnc.html?host=127.0.0.1&port=${NOVNC_PORT}&autoconnect=1&resize=scale"
APP_PATTERN='C:\\Program Files \(x86\)\\WXWork\\WXWork.exe'

mkdir -p "$PRIVATE" "$LOG_DIR"

is_running() {
  pgrep -u "${USER:-$(id -un)}" -f "$APP_PATTERN" >/dev/null 2>&1
}

emit() {
  local ok="$1"
  local error="${2:-}"
  local installed=false
  local running=false
  [[ -f "$EXE_UNIX" ]] && installed=true
  is_running && running=true
  if [[ "$JSON" == "1" ]]; then
    python3 - "$ok" "$ACTION" "$installed" "$running" "$NOVNC_URL" "$error" <<'PY'
import json
import sys

print(json.dumps({
    "ok": sys.argv[1] == "true",
    "action": sys.argv[2],
    "installed": sys.argv[3] == "true",
    "running": sys.argv[4] == "true",
    "novnc_url": sys.argv[5],
    "error": sys.argv[6],
}, ensure_ascii=False, sort_keys=True))
PY
  else
    printf 'installed=%s running=%s\nnoVNC: %s\n' "$installed" "$running" "$NOVNC_URL"
    [[ -z "$error" ]] || printf 'error: %s\n' "$error" >&2
  fi
}

launch_desktop() {
  "$ROOT/agentic_tools/virtual_desktop/launch_virtual_desktop.sh" \
    --name wecom-client \
    --display "$DISPLAY_ID" \
    --vnc-port "$VNC_PORT" \
    --novnc-port "$NOVNC_PORT" \
    --log-dir "$LOG_DIR" >"$LOG_DIR/desktop.log" 2>&1
}

download_installer() {
  [[ -s "$INSTALLER" ]] && return 0
  if command -v aria2c >/dev/null 2>&1; then
    aria2c --continue=true --max-connection-per-server=8 --split=8 \
      --min-split-size=4M --file-allocation=none \
      --dir="$(dirname "$INSTALLER")" --out="$(basename "$INSTALLER")" \
      "$DOWNLOAD_URL" >"$LOG_DIR/download.log" 2>&1
  elif command -v curl >/dev/null 2>&1; then
    curl -fL --retry 3 --continue-at - "$DOWNLOAD_URL" -o "$INSTALLER" \
      >"$LOG_DIR/download.log" 2>&1
  else
    return 1
  fi
}

install_client() {
  command -v wine >/dev/null 2>&1 || return 1
  download_installer || return 1
  launch_desktop
  if [[ ! -f "$PREFIX/system.reg" ]]; then
    env DISPLAY="$DISPLAY_ID" XAUTHORITY= WINEPREFIX="$PREFIX" WINEARCH=win64 \
      WINEDLLOVERRIDES='mscoree,mshtml=' wineboot -u \
      >"$LOG_DIR/wineboot.log" 2>&1
  fi
  env DISPLAY="$DISPLAY_ID" XAUTHORITY= WINEPREFIX="$PREFIX" \
    WINEDLLOVERRIDES='mscoree,mshtml=' wine "$INSTALLER" /S \
    >"$LOG_DIR/install.log" 2>&1
  [[ -f "$EXE_UNIX" ]]
}

start_client() {
  [[ -f "$EXE_UNIX" ]] || return 1
  launch_desktop
  if ! is_running; then
    env DISPLAY="$DISPLAY_ID" XAUTHORITY= WINEPREFIX="$PREFIX" WINEDEBUG=-all \
      WINEDLLOVERRIDES='mscoree,mshtml=' setsid wine "$EXE_WINDOWS" \
      >"$LOG_DIR/app.log" 2>&1 < /dev/null &
  fi
  for _ in $(seq 1 30); do
    is_running && return 0
    sleep 0.5
  done
  return 1
}

case "$ACTION" in
  status)
    emit true
    ;;
  download)
    if download_installer; then emit true; else emit false "official WeCom client download failed"; exit 1; fi
    ;;
  install)
    if install_client; then emit true; else emit false "official WeCom client installation failed"; exit 1; fi
    ;;
  start)
    if start_client; then emit true; else emit false "official WeCom client is not installed or did not start"; exit 1; fi
    ;;
  *)
    emit false "unknown action: $ACTION"
    exit 2
    ;;
esac
