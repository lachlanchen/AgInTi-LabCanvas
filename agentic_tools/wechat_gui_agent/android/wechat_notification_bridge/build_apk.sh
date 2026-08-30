#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
BUILD_TOOLS_VERSION="${ANDROID_BUILD_TOOLS_VERSION:-36.1.0}"
PLATFORM_VERSION="${ANDROID_PLATFORM_VERSION:-android-34}"
TOOLS="$SDK_ROOT/build-tools/$BUILD_TOOLS_VERSION"
ANDROID_JAR="$SDK_ROOT/platforms/$PLATFORM_VERSION/android.jar"
BUILD="$ROOT/build"
APK="$BUILD/labcanvas-wechat-notification-bridge.apk"
UNSIGNED="$BUILD/unsigned.apk"
UNALIGNED="$BUILD/unaligned.apk"
DEX="$BUILD/dex"
CLASSES="$BUILD/classes"
CLASSES_JAR="$BUILD/classes.jar"
KEYSTORE="${ANDROID_DEBUG_KEYSTORE:-$HOME/.android/debug.keystore}"

for tool in aapt2 d8 zipalign apksigner; do
  [[ -x "$TOOLS/$tool" ]] || { echo "Missing Android build tool: $TOOLS/$tool" >&2; exit 2; }
done
[[ -f "$ANDROID_JAR" ]] || { echo "Missing Android platform: $ANDROID_JAR" >&2; exit 2; }
[[ -f "$KEYSTORE" ]] || { echo "Missing Android debug keystore: $KEYSTORE" >&2; exit 2; }

rm -rf "$BUILD"
mkdir -p "$BUILD" "$DEX" "$CLASSES"

"$TOOLS/aapt2" link \
  -o "$UNALIGNED" \
  -I "$ANDROID_JAR" \
  --manifest "$ROOT/AndroidManifest.xml" \
  --min-sdk-version 26 \
  --target-sdk-version 29

mapfile -t sources < <(find "$ROOT/src" -type f -name '*.java' -print | sort)
javac -encoding UTF-8 -source 8 -target 8 -bootclasspath "$ANDROID_JAR" \
  -d "$CLASSES" "${sources[@]}"
jar --create --file "$CLASSES_JAR" -C "$CLASSES" .
"$TOOLS/d8" --lib "$ANDROID_JAR" --min-api 26 --output "$DEX" "$CLASSES_JAR"
cp "$UNALIGNED" "$UNSIGNED"
(cd "$DEX" && zip -q -j "$UNSIGNED" classes.dex)
"$TOOLS/zipalign" -f 4 "$UNSIGNED" "$APK"
"$TOOLS/apksigner" sign \
  --ks "$KEYSTORE" \
  --ks-key-alias androiddebugkey \
  --ks-pass pass:android \
  --key-pass pass:android \
  "$APK"
"$TOOLS/apksigner" verify "$APK"
printf '%s\n' "$APK"
