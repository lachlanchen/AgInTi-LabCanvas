#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
PRIVATE_ROOT="$ROOT/agentic_tools/wecom_agent/.private"
APK="$PRIVATE_ROOT/WeCom_android_official.apk"
PACKAGE="com.tencent.wework"
DOWNLOAD_URL="https://work.weixin.qq.com/wework_admin/commdownload?platform=android&from=labcanvas"
SERIAL="${ANDROID_SERIAL:-}"
ACTION="${1:-status}"
POLL_SECONDS="${WECOM_ANDROID_SETUP_POLL_SECONDS:-10}"
TIMEOUT_SECONDS="${WECOM_ANDROID_SETUP_TIMEOUT_SECONDS:-86400}"
DISABLE_HOST_AUTOMOUNT="${WECOM_ANDROID_DISABLE_HOST_AUTOMOUNT:-1}"

usage() {
  cat <<'EOF'
Usage: wecom_android_setup.sh prepare|status|install|wait-install|open|mirror [--serial SERIAL]

Downloads the official WeCom Android client to an ignored private directory.
Installation waits for the owner to unlock a secure keyguard; it never tries
to bypass a PIN, password, pattern, or biometric lock.
EOF
}

shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --serial) SERIAL="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

resolve_serial() {
  if [[ -n "$SERIAL" ]]; then
    printf '%s\n' "$SERIAL"
    return
  fi
  mapfile -t devices < <(adb devices | awk 'NR > 1 && $2 == "device" {print $1}')
  if [[ "${#devices[@]}" -ne 1 ]]; then
    echo "Expected exactly one authorized Android device; pass --serial." >&2
    exit 3
  fi
  printf '%s\n' "${devices[0]}"
}

disable_host_media_automount() {
  [[ "$DISABLE_HOST_AUTOMOUNT" == "1" ]] || return 0
  command -v gsettings >/dev/null 2>&1 || return 0
  # The mobile relay uses ADB. GNOME's MTP automount is unnecessary and can
  # raise an org.freedesktop.udisks2.filesystem-mount-other-seat password
  # dialog when the dedicated phone reconnects from another desktop seat.
  gsettings set org.gnome.desktop.media-handling automount false >/dev/null 2>&1 || true
  gsettings set org.gnome.desktop.media-handling automount-open false >/dev/null 2>&1 || true
}

package_installed() {
  adb -s "$1" shell pm list packages "$PACKAGE" | grep -qx "package:$PACKAGE"
}

keyguard_locked() {
  adb -s "$1" shell dumpsys window | grep -q 'isStatusBarKeyguard=true'
}

prepare_apk() {
  mkdir -p "$PRIVATE_ROOT"
  chmod 700 "$PRIVATE_ROOT"
  if [[ -s "$APK" ]]; then
    echo "Official WeCom APK already present: $APK"
    return
  fi
  final_url="$(curl -LfsS -o /dev/null -w '%{url_effective}' "$DOWNLOAD_URL")"
  case "$final_url" in
    https://dldir1.qq.com/wework/*) ;;
    *) echo "Refusing unexpected WeCom APK host: $final_url" >&2; exit 4 ;;
  esac
  curl -L --fail --retry 3 --retry-delay 2 "$final_url" -o "$APK"
  chmod 600 "$APK"
  file "$APK" | grep -q 'Android package' || {
    rm -f "$APK"
    echo "Downloaded file is not an Android APK." >&2
    exit 5
  }
  echo "Downloaded official WeCom APK: $APK"
}

install_apk() {
  serial="$1"
  prepare_apk
  if package_installed "$serial"; then
    echo "WeCom is already installed on $serial."
    return
  fi
  if keyguard_locked "$serial"; then
    echo "Secure Android keyguard is locked; unlock the phone before installation." >&2
    return 6
  fi
  adb -s "$serial" install -r -g "$APK"
  package_installed "$serial" || {
    echo "WeCom installation did not produce package $PACKAGE." >&2
    exit 7
  }
  echo "Installed WeCom on $serial."
}

open_wecom() {
  serial="$1"
  disable_host_media_automount
  package_installed "$serial" || {
    echo "WeCom is not installed on $serial." >&2
    exit 8
  }
  adb -s "$serial" shell svc power stayon true >/dev/null
  adb -s "$serial" shell monkey -p "$PACKAGE" -c android.intent.category.LAUNCHER 1 >/dev/null
  echo "Opened WeCom on $serial."
}

case "$ACTION" in
  prepare)
    disable_host_media_automount
    prepare_apk
    ;;
  status)
    serial="$(resolve_serial)"
    printf 'serial=%s\ninstalled=%s\nkeyguard_locked=%s\n' \
      "$serial" \
      "$(package_installed "$serial" && echo true || echo false)" \
      "$(keyguard_locked "$serial" && echo true || echo false)"
    ;;
  install)
    serial="$(resolve_serial)"
    install_apk "$serial"
    open_wecom "$serial"
    ;;
  wait-install)
    serial="$(resolve_serial)"
    deadline=$((SECONDS + TIMEOUT_SECONDS))
    while keyguard_locked "$serial"; do
      if (( SECONDS >= deadline )); then
        echo "Timed out waiting for the owner to unlock the Android keyguard." >&2
        exit 9
      fi
      sleep "$POLL_SECONDS"
    done
    install_apk "$serial"
    open_wecom "$serial"
    ;;
  open)
    serial="$(resolve_serial)"
    open_wecom "$serial"
    ;;
  mirror)
    serial="$(resolve_serial)"
    disable_host_media_automount
    "$ROOT/agentic_tools/android_device_agent/scripts/android_device_desktop.sh" restart --serial "$serial"
    if package_installed "$serial" && ! keyguard_locked "$serial"; then
      open_wecom "$serial"
    fi
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
