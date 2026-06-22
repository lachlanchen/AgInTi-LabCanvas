#!/usr/bin/env bash
set -euo pipefail

AVD_NAME="${MIX2S_AVD_NAME:-LabCanvas_MIX2S_API34}"
PACKAGE="${MIX2S_AVD_PACKAGE:-system-images;android-34;default;x86_64}"
DEVICE="${MIX2S_AVD_DEVICE:-pixel_2}"

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 3
  fi
}

need avdmanager
need sdkmanager

if avdmanager list avd | grep -Eq "^ +Name: ${AVD_NAME}$"; then
  echo "AVD already exists: $AVD_NAME"
else
  set +o pipefail
  printf 'no\n' | avdmanager create avd --name "$AVD_NAME" --package "$PACKAGE" --device "$DEVICE" --sdcard 2048M
  create_status="${PIPESTATUS[1]}"
  set -o pipefail
  if [[ "$create_status" != "0" ]]; then
    exit "$create_status"
  fi
fi

CONFIG="$HOME/.android/avd/${AVD_NAME}.avd/config.ini"
if [[ ! -f "$CONFIG" ]]; then
  echo "Missing AVD config: $CONFIG" >&2
  exit 4
fi

set_prop() {
  key="$1"
  value="$2"
  if grep -q "^${key}=" "$CONFIG"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$CONFIG"
  else
    printf '%s=%s\n' "$key" "$value" >>"$CONFIG"
  fi
}

set_prop hw.lcd.width 1080
set_prop hw.lcd.height 2160
set_prop hw.lcd.density 440
set_prop hw.ramSize 4096
set_prop disk.dataPartition.size 4096M
set_prop hw.keyboard yes
set_prop showDeviceFrame no

echo "Ready: $AVD_NAME"
echo "Launch: emulator -avd $AVD_NAME -no-snapshot-load"
