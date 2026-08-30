#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$ROOT/../../../.." && pwd -P)"
SERIAL="${ANDROID_SERIAL:-${1:-}}"
PACKAGE="art.lazying.labcanvas.wechatbridge"
COMPONENT="$PACKAGE/.WechatNotificationListener"
CANONICAL_COMPONENT="$PACKAGE/$PACKAGE.WechatNotificationListener"
BOOTSTRAP_COMPONENT="$PACKAGE/.BootstrapReceiver"
MIX2S="$PROJECT_ROOT/scripts/mix2s"

if [[ -z "$SERIAL" ]]; then
  mapfile -t devices < <(adb devices | awk 'NR > 1 && $2 == "device" {print $1}')
  [[ "${#devices[@]}" -eq 1 ]] || { echo "Set ANDROID_SERIAL when more than one device is connected." >&2; exit 2; }
  SERIAL="${devices[0]}"
fi

restore_dual=false
if [[ -x "$MIX2S" ]]; then
  mix2s_status="$($MIX2S status --serial "$SERIAL" 2>/dev/null || true)"
  if [[ "$mix2s_status" == *"status: running"* && "$mix2s_status" == *"layout: dual"* ]]; then
    restore_dual=true
  fi
fi

restore_layout() {
  local status=$?
  if [[ "$restore_dual" == true ]]; then
    # MIUI finishes its USB-install transition asynchronously after adb exits.
    sleep 4
    "$MIX2S" dual --serial "$SERIAL" >/dev/null 2>&1 || true
    for _ in $(seq 1 5); do
      sleep 2
      mix2s_status="$($MIX2S status --serial "$SERIAL" 2>/dev/null || true)"
      if [[ "$mix2s_status" == *"dual displays: online (WeChat physical, WeCom virtual)"* ]]; then
        break
      fi
      "$MIX2S" dual --serial "$SERIAL" >/dev/null 2>&1 || true
    done
  fi
  return "$status"
}
trap restore_layout EXIT

APK="$($ROOT/build_apk.sh)"
python3 "$ROOT/install_bridge.py" --serial "$SERIAL" --apk "$APK"
adb -s "$SERIAL" shell am broadcast \
  -f 0x20 \
  -a art.lazying.labcanvas.wechatbridge.BOOTSTRAP \
  -n "$BOOTSTRAP_COMPONENT" >/dev/null

baseline_lines="$(
  { adb -s "$SERIAL" exec-out run-as "$PACKAGE" cat files/events.jsonl 2>/dev/null || true; } \
    | wc -l | tr -dc '0-9'
)"
baseline_lines="${baseline_lines:-0}"

adb -s "$SERIAL" shell cmd notification disallow_listener "$CANONICAL_COMPONENT" >/dev/null 2>&1 || true
adb -s "$SERIAL" shell cmd notification allow_listener "$CANONICAL_COMPONENT"

listener_connected=false
for _ in $(seq 1 20); do
  if adb -s "$SERIAL" exec-out run-as "$PACKAGE" cat files/events.jsonl 2>/dev/null \
      | tail -n "+$((baseline_lines + 1))" \
      | grep -F '"kind":"listener_connected"' >/dev/null; then
    listener_connected=true
    break
  fi
  sleep 0.5
done

approved="$(adb -s "$SERIAL" shell settings get secure enabled_notification_listeners | tr -d '\r')"
if [[ "$approved" != *"$COMPONENT"* && "$approved" != *"$CANONICAL_COMPONENT"* ]]; then
  echo "Notification listener was not enabled." >&2
  exit 3
fi
[[ "$listener_connected" == true ]] || { echo "Notification listener did not become live." >&2; exit 4; }
printf 'installed=%s\nlistener=%s\nlive=true\nserial=%s\n' \
  "$PACKAGE" "$CANONICAL_COMPONENT" "$SERIAL"
