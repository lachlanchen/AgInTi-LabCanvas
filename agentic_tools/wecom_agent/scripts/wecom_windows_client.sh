#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
SELF="$ROOT/agentic_tools/wecom_agent/scripts/wecom_windows_client.sh"
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
AUTOFIT_PID_FILE="$LOG_DIR/autofit.pid"
LOGIN_FALLBACK_STAMP="$LOG_DIR/login-fallback.stamp"
DOWNLOAD_URL="${WECOM_CLIENT_DOWNLOAD_URL:-https://work.weixin.qq.com/wework_admin/commdownload?platform=win&from=wwindex}"
EXE_UNIX="$PREFIX/drive_c/Program Files (x86)/WXWork/WXWork.exe"
EXE_WINDOWS='C:\Program Files (x86)\WXWork\WXWork.exe'
NOVNC_URL="http://127.0.0.1:${NOVNC_PORT}/vnc.html?host=127.0.0.1&port=${NOVNC_PORT}&autoconnect=1&resize=scale"
APP_PATTERN='C:\\Program Files \(x86\)\\WXWork\\WXWork.exe'
LAYERED_NATIVE_GEOMETRY="${WECOM_CLIENT_LAYERED_NATIVE_GEOMETRY:-1}"

mkdir -p "$PRIVATE" "$LOG_DIR"

is_running() {
  pgrep -u "${USER:-$(id -un)}" -f "$APP_PATTERN" >/dev/null 2>&1
}

is_autofit_running() {
  [[ -s "$AUTOFIT_PID_FILE" ]] || return 1
  kill -0 "$(cat "$AUTOFIT_PID_FILE")" >/dev/null 2>&1
}

has_visible_client_window() {
  command -v xdotool >/dev/null 2>&1 || return 1
  env DISPLAY="$DISPLAY_ID" XAUTHORITY= xdotool search --onlyvisible \
    --name 'WeCom|企业微信' 2>/dev/null | head -n 1 | grep -q .
}

login_fallback_due() {
  [[ -e "$LOGIN_FALLBACK_STAMP" ]] || return 0
  local now modified
  now="$(date +%s)"
  modified="$(stat -c %Y "$LOGIN_FALLBACK_STAMP" 2>/dev/null || printf '0')"
  (( now - modified >= 60 ))
}

wait_for_client_window() {
  local attempts="${1:-30}"
  local stable_checks=0
  for _ in $(seq 1 "$attempts"); do
    if is_running && has_visible_client_window; then
      stable_checks=$((stable_checks + 1))
      if (( stable_checks >= 4 )); then
        return 0
      fi
    else
      stable_checks=0
    fi
    sleep 0.5
  done
  return 1
}

emit() {
  local ok="$1"
  local error="${2:-}"
  local installed=false
  local running=false
  local autofit_running=false
  [[ -f "$EXE_UNIX" ]] && installed=true
  is_running && running=true
  is_autofit_running && autofit_running=true
  if [[ "$JSON" == "1" ]]; then
    python3 - "$ok" "$ACTION" "$installed" "$running" "$autofit_running" "$NOVNC_URL" "$error" <<'PY'
import json
import sys

print(json.dumps({
    "ok": sys.argv[1] == "true",
    "action": sys.argv[2],
    "installed": sys.argv[3] == "true",
    "running": sys.argv[4] == "true",
    "autofit_running": sys.argv[5] == "true",
    "novnc_url": sys.argv[6],
    "error": sys.argv[7],
}, ensure_ascii=False, sort_keys=True))
PY
  else
    printf 'installed=%s running=%s autofit=%s\nnoVNC: %s\n' \
      "$installed" "$running" "$autofit_running" "$NOVNC_URL"
    [[ -z "$error" ]] || printf 'error: %s\n' "$error" >&2
  fi
}

fit_client_window() {
  command -v xdotool >/dev/null 2>&1 || return 1
  local window_id=""
  local candidate=""
  local geometry=""
  local candidate_width=0
  local candidate_height=0
  local candidate_area=0
  local best_area=0
  local width=0
  local height=0
  local screen_width=1920
  local screen_height=1080
  local x=0
  local y=0
  local windows=()

  mapfile -t windows < <(
    env DISPLAY="$DISPLAY_ID" XAUTHORITY= xdotool search --onlyvisible --name 'WeCom|企业微信' 2>/dev/null || true
  )
  if [[ ${#windows[@]} -eq 0 ]]; then
    mapfile -t windows < <(
      env DISPLAY="$DISPLAY_ID" XAUTHORITY= xdotool search --onlyvisible --class 'wxwork.exe' 2>/dev/null || true
    )
  fi
  for candidate in "${windows[@]}"; do
    geometry="$(env DISPLAY="$DISPLAY_ID" XAUTHORITY= xdotool getwindowgeometry --shell "$candidate" 2>/dev/null || true)"
    candidate_width="$(awk -F= '$1 == "WIDTH" {print $2}' <<<"$geometry")"
    candidate_height="$(awk -F= '$1 == "HEIGHT" {print $2}' <<<"$geometry")"
    [[ "$candidate_width" =~ ^[0-9]+$ && "$candidate_height" =~ ^[0-9]+$ ]] || continue
    candidate_area=$((candidate_width * candidate_height))
    if (( candidate_area > best_area )); then
      best_area="$candidate_area"
      window_id="$candidate"
      width="$candidate_width"
      height="$candidate_height"
    fi
  done
  [[ -n "$window_id" ]] || return 1

  read -r screen_width screen_height < <(
    env DISPLAY="$DISPLAY_ID" XAUTHORITY= xdotool getdisplaygeometry
  )
  if (( width >= 600 && height >= 500 )) && [[ "$LAYERED_NATIVE_GEOMETRY" == "1" ]]; then
    # WeCom under Wine renders one logical window through several synchronized
    # top-level layers. Moving or resizing only the named layer separates the
    # content from its frame. Keep the application's native geometry and let
    # the full noVNC client scale the complete X desktop instead.
    return 0
  elif (( width >= 600 && height >= 500 )); then
    env DISPLAY="$DISPLAY_ID" XAUTHORITY= xdotool \
      windowmap "$window_id" \
      windowmove --sync "$window_id" 0 0 \
      windowsize --sync "$window_id" "$screen_width" "$screen_height" \
      windowraise "$window_id" >/dev/null 2>&1 || true
  else
    x=$(((screen_width - width) / 2))
    y=$(((screen_height - height) / 2))
    (( x < 0 )) && x=0
    (( y < 0 )) && y=0
    env DISPLAY="$DISPLAY_ID" XAUTHORITY= xdotool \
      windowmap "$window_id" \
      windowmove --sync "$window_id" "$x" "$y" \
      windowraise "$window_id" >/dev/null 2>&1 || true
  fi
}

autofit_loop() {
  while is_running; do
    fit_client_window || true
    sleep 2
  done
}

start_autofit_guard() {
  is_autofit_running && return 0
  env DISPLAY="$DISPLAY_ID" XAUTHORITY= setsid "$SELF" autofit-loop \
    >>"$LOG_DIR/autofit.log" 2>&1 < /dev/null &
  echo "$!" >"$AUTOFIT_PID_FILE"
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
  if is_running && wait_for_client_window 4; then
    start_autofit_guard
    fit_client_window || true
    return 0
  fi
  if ! is_running; then
    env DISPLAY="$DISPLAY_ID" XAUTHORITY= WINEPREFIX="$PREFIX" WINEDEBUG=-all \
      WINEDLLOVERRIDES='mscoree,mshtml=' setsid wine "$EXE_WINDOWS" \
      >"$LOG_DIR/app.log" 2>&1 < /dev/null &
  fi
  if wait_for_client_window 30; then
    start_autofit_guard
    fit_client_window || true
    return 0
  fi

  # Never enter account-switch mode from the supervisor. A hidden or crashed
  # layered window is not evidence that authentication expired; doing so can
  # invalidate an otherwise reusable desktop session.
  return 1
}

show_login_qr() {
  [[ -f "$EXE_UNIX" ]] || return 1
  launch_desktop
  if ! login_fallback_due; then
    return 0
  fi
  touch "$LOGIN_FALLBACK_STAMP"
  env DISPLAY="$DISPLAY_ID" XAUTHORITY= WINEPREFIX="$PREFIX" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' setsid wine "$EXE_WINDOWS" \
    >"$LOG_DIR/app-login-broker.log" 2>&1 < /dev/null &
  sleep 1
  env DISPLAY="$DISPLAY_ID" XAUTHORITY= WINEPREFIX="$PREFIX" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' setsid wine "$EXE_WINDOWS" \
    --switch-account --from-broker --we-channel=676 --we-ppid="$$" \
    --skia_enable --skia_text_enable --skia_enable_win7 \
    >"$LOG_DIR/app-switch-account.log" 2>&1 < /dev/null &
  wait_for_client_window 30
}

supervise_client() {
  trap 'exit 0' INT TERM
  while true; do
    start_client || true
    sleep 10
  done
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
  login)
    if show_login_qr; then emit true; else emit false "WeCom login window did not open"; exit 1; fi
    ;;
  fit)
    if fit_client_window; then emit true; else emit false "WeCom window was not found"; exit 1; fi
    ;;
  supervise)
    supervise_client
    ;;
  autofit-loop)
    autofit_loop
    ;;
  *)
    emit false "unknown action: $ACTION"
    exit 2
    ;;
esac
