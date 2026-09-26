#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

PACKAGE="nl.zennay.raiseai"
SDK_DIR="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}"
ADB="$SDK_DIR/platform-tools/adb"
JAVA_HOME="${JAVA_HOME:-/Applications/Android Studio.app/Contents/jbr/Contents/Home}"
export JAVA_HOME
export PATH="$JAVA_HOME/bin:$SDK_DIR/platform-tools:$PATH"

if [ ! -x "$JAVA_HOME/bin/java" ]; then
  echo "Android Studio Java not found at: $JAVA_HOME"
  exit 1
fi
if [ ! -x "$ADB" ]; then
  echo "adb not found at: $ADB"
  exit 1
fi
if [ ! -f "$SDK_DIR/platforms/android-35/android.jar" ]; then
  echo "Android SDK Platform 35 not found under: $SDK_DIR"
  exit 1
fi
printf 'sdk.dir=%s\n' "$SDK_DIR" > local.properties

find_watch() {
  "$ADB" devices -l | awk 'NR>1 && $2=="device" {print $1}' | while IFS= read -r serial; do
    [ -z "$serial" ] && continue
    features="$($ADB -s "$serial" shell pm list features 2>/dev/null | tr -d '\r' || true)"
    model="$($ADB -s "$serial" shell getprop ro.product.model 2>/dev/null | tr -d '\r' || true)"
    device="$($ADB -s "$serial" shell getprop ro.product.device 2>/dev/null | tr -d '\r' || true)"
    if printf '%s\n' "$features" | grep -q 'android.hardware.type.watch' || [ "$model" = "SM_L315F" ] || printf '%s' "$device" | grep -qi '^fresh'; then
      printf '%s\n' "$serial"
      return 0
    fi
  done
}

TARGET="${ANDROID_SERIAL:-$(find_watch | head -n 1)}"
if [ -z "$TARGET" ]; then
  echo "No connected Wear OS watch found."
  echo "On the Watch: Developer options → Wireless debugging, then connect it with adb first."
  echo
  "$ADB" devices -l
  exit 1
fi

MODEL="$($ADB -s "$TARGET" shell getprop ro.product.model | tr -d '\r')"
echo "Watch: $MODEL ($TARGET)"
echo "Building Raise AI v1.0…"
echo "First build downloads the bundled GeckoView browser engine and can take several minutes."
./gradlew :app:assembleDebug

echo "Installing APK directly on the Watch…"
"$ADB" -s "$TARGET" install -r app/build/outputs/apk/debug/app-debug.apk

echo "Applying personal sideload grants…"
"$ADB" -s "$TARGET" shell appops set "$PACKAGE" SYSTEM_ALERT_WINDOW allow || true
"$ADB" -s "$TARGET" shell appops set "$PACKAGE" GET_USAGE_STATS allow || true

echo "Opening Raise AI…"
"$ADB" -s "$TARGET" shell am start -n "$PACKAGE/.MainActivity" >/dev/null

# install -r preserves app data. If monitoring was enabled before the upgrade,
# ACTION_MY_PACKAGE_REPLACED will attempt to restore the foreground service.

echo
echo "Permission check:"
"$ADB" -s "$TARGET" shell appops get "$PACKAGE" SYSTEM_ALERT_WINDOW 2>/dev/null || true
"$ADB" -s "$TARGET" shell appops get "$PACKAGE" GET_USAGE_STATS 2>/dev/null || true

echo
echo "Raise AI v1.0 installed."
echo "Test: tap 'Open RaiseGPT Wear UI', sign in once, allow the microphone, then try a fresh raise."
echo "Gemini remains available separately for Google Home commands."
echo "Sleep/DND pause is ON by default; the sensor is paused while Watch DND/Bedtime is active."
