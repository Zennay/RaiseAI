#!/bin/bash
set -euo pipefail

PACKAGE="nl.zennay.raiseai"
EXPECTED_ABI="armeabi-v7a"
if [ -n "${ANDROID_SDK_ROOT:-}" ]; then
  SDK_DIR="$ANDROID_SDK_ROOT"
elif [ -n "${ANDROID_HOME:-}" ]; then
  SDK_DIR="$ANDROID_HOME"
elif [ "$(uname -s)" = "Darwin" ] && [ -d "$HOME/Library/Android/sdk" ]; then
  SDK_DIR="$HOME/Library/Android/sdk"
else
  SDK_DIR="$HOME/Android/Sdk"
fi
ADB="$SDK_DIR/platform-tools/adb"
APK="${1:-}"
CONNECT_ENDPOINT="${2:-${WATCH_ENDPOINT:-}}"

if [ -z "$APK" ]; then
  echo "Usage: ./install-watch-apk.command /path/to/RaiseAI.apk [watch-ip:port]"
  exit 2
fi
[ -x "$ADB" ] || { echo "adb not found at: $ADB"; exit 1; }
[ -f "$APK" ] || { echo "APK not found: $APK"; exit 1; }
command -v unzip >/dev/null || { echo "unzip is required"; exit 1; }

"$ADB" start-server >/dev/null

try_mdns_connect() {
  local endpoint=""
  endpoint="$("$ADB" mdns services 2>/dev/null | awk '/_adb-tls-connect[.]_tcp/ {print $3; exit}' || true)"
  if [ -n "${endpoint:-}" ]; then
    echo "Trying Watch reconnect via ${endpoint}..."
    "$ADB" connect "$endpoint" >/dev/null 2>&1 || true
  fi
}

find_watch() {
  local serial="" model="" device="" features=""
  "$ADB" devices -l | awk 'NR>1 && $2=="device" {print $1}' | while IFS= read -r serial; do
    [ -z "${serial:-}" ] && continue
    model="$("$ADB" -s "$serial" shell getprop ro.product.model 2>/dev/null | tr -d '\r' || true)"
    device="$("$ADB" -s "$serial" shell getprop ro.product.device 2>/dev/null | tr -d '\r' || true)"
    features="$("$ADB" -s "$serial" shell pm list features 2>/dev/null | tr -d '\r' || true)"
    if [ "$model" = "SM_L315F" ] || printf '%s' "$device" | grep -qi '^fresh' ||
       printf '%s\n' "$features" | grep -q 'android.hardware.type.watch'; then
      printf '%s\n' "$serial"
      return 0
    fi
  done
}

TARGET="${ANDROID_SERIAL:-$(find_watch | head -n 1)}"
if [ -z "$TARGET" ] && [ -n "${CONNECT_ENDPOINT:-}" ]; then
  echo "Connecting to Watch via ${CONNECT_ENDPOINT}..."
  "$ADB" connect "$CONNECT_ENDPOINT" >/dev/null 2>&1 || true
  sleep 1
  TARGET="${ANDROID_SERIAL:-$(find_watch | head -n 1)}"
fi
if [ -z "$TARGET" ]; then
  try_mdns_connect
  sleep 1
  TARGET="${ANDROID_SERIAL:-$(find_watch | head -n 1)}"
fi

if [ -z "$TARGET" ]; then
  echo "No connected Wear OS watch found."
  echo "On the Watch: Developer options → Wireless debugging → ON."
  echo "If already paired, pass the general Wireless debugging IP:port as the second argument."
  echo "Example: ./install-watch-apk.command RaiseAI.apk 192.168.1.219:12345"
  "$ADB" devices -l
  exit 1
fi

MODEL="$("$ADB" -s "$TARGET" shell getprop ro.product.model | tr -d '\r')"
WATCH_ABI="$("$ADB" -s "$TARGET" shell getprop ro.product.cpu.abi | tr -d '\r')"
WATCH_ABILIST="$("$ADB" -s "$TARGET" shell getprop ro.product.cpu.abilist | tr -d '\r')"
APK_ABIS="$(unzip -Z1 "$APK" | awk -F/ '$1=="lib" && $NF ~ /[.]so$/ {print $2}' | sort -u)"

echo "Watch: $MODEL ($TARGET)"
echo "Watch ABI: $WATCH_ABI"
echo "Watch ABI list: $WATCH_ABILIST"
echo "APK ABI(s):"
printf '%s\n' "$APK_ABIS"

if [ "$APK_ABIS" != "$EXPECTED_ABI" ]; then
  echo "ERROR: Refusing install. Race AI Watch APK must contain exactly: $EXPECTED_ABI"
  exit 1
fi
if [ "$WATCH_ABI" != "$EXPECTED_ABI" ]; then
  echo "ERROR: Watch ABI is $WATCH_ABI but this APK targets $EXPECTED_ABI."
  exit 1
fi

install_once() {
  "$ADB" -s "$TARGET" install --no-streaming -r "$APK"
}

echo "Installing verified Race AI APK…"
if ! install_once; then
  echo "Install connection failed; trying one automatic reconnect…"
  try_mdns_connect
  sleep 1
  TARGET="${ANDROID_SERIAL:-$(find_watch | head -n 1)}"
  [ -n "$TARGET" ] || { echo "Watch did not reconnect."; exit 1; }
  install_once
fi

echo "Applying sideload grants…"
"$ADB" -s "$TARGET" shell appops set "$PACKAGE" SYSTEM_ALERT_WINDOW allow || true
"$ADB" -s "$TARGET" shell appops set "$PACKAGE" GET_USAGE_STATS allow || true

echo "Opening Race AI…"
"$ADB" -s "$TARGET" shell am start -n "$PACKAGE/.MainActivity" >/dev/null

echo
echo "Installed package:"
"$ADB" -s "$TARGET" shell dumpsys package "$PACKAGE" |
  grep -E "versionName=|versionCode=" | head -2

echo "Race AI installation complete."