#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

SDK_DIR="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}"
ADB="$SDK_DIR/platform-tools/adb"
JAVA_HOME="${JAVA_HOME:-/Applications/Android Studio.app/Contents/jbr/Contents/Home}"
export JAVA_HOME
export PATH="$JAVA_HOME/bin:$SDK_DIR/platform-tools:$PATH"

[ -x "$JAVA_HOME/bin/java" ] || {
  echo "Android Studio Java not found at: $JAVA_HOME"
  exit 1
}
[ -x "$ADB" ] || { echo "adb not found at: $ADB"; exit 1; }
[ -f "$SDK_DIR/platforms/android-35/android.jar" ] || {
  echo "Android SDK Platform 35 not found under: $SDK_DIR"
  exit 1
}

printf 'sdk.dir=%s\n' "$SDK_DIR" > local.properties
VERSION="$(tr -d '\r\n' < VERSION.txt)"

echo "Building Race AI v$VERSION…"
echo "The build will fail automatically if the Watch ABI is wrong."
./gradlew :app:assembleDebug

exec ./install-watch-apk.command app/build/outputs/apk/debug/app-debug.apk