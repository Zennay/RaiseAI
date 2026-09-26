#!/bin/bash
set -euo pipefail

PACKAGE="nl.zennay.raiseai"
EXPECTED_ABI="armeabi-v7a"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="$HOME/.raiseai"
ENDPOINT_FILE="$STATE_DIR/watch-endpoint"
SIGNING_DIR="$STATE_DIR/signing"
mkdir -p "$STATE_DIR" "$SIGNING_DIR"

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

connect_endpoint() {
  local endpoint="${1:-}"
  [ -n "$endpoint" ] || return 1
  echo "Connecting to Watch via $endpoint..."
  "$ADB" connect "$endpoint" >/dev/null 2>&1 || return 1
  sleep 1
  return 0
}

mdns_endpoint() {
  "$ADB" mdns services 2>/dev/null |
    awk '/_adb-tls-connect[.]_tcp/ {print $3; exit}' || true
}

TARGET="${ANDROID_SERIAL:-$(find_watch)}"
LAST_ENDPOINT=""

if [ -z "$TARGET" ] && [ -n "${CONNECT_ENDPOINT:-}" ]; then
  connect_endpoint "$CONNECT_ENDPOINT" || true
  LAST_ENDPOINT="$CONNECT_ENDPOINT"
  TARGET="${ANDROID_SERIAL:-$(find_watch)}"
fi

if [ -z "$TARGET" ] && [ -f "$ENDPOINT_FILE" ]; then
  CACHED_ENDPOINT="$(tr -d '\r\n' < "$ENDPOINT_FILE")"
  if [ -n "$CACHED_ENDPOINT" ]; then
    connect_endpoint "$CACHED_ENDPOINT" || true
    LAST_ENDPOINT="$CACHED_ENDPOINT"
    TARGET="${ANDROID_SERIAL:-$(find_watch)}"
  fi
fi

if [ -z "$TARGET" ]; then
  DISCOVERED_ENDPOINT="$(mdns_endpoint)"
  if [ -n "${DISCOVERED_ENDPOINT:-}" ]; then
    connect_endpoint "$DISCOVERED_ENDPOINT" || true
    LAST_ENDPOINT="$DISCOVERED_ENDPOINT"
    TARGET="${ANDROID_SERIAL:-$(find_watch)}"
  fi
fi

if [ -z "$TARGET" ]; then
  echo "No connected Wear OS watch found."
  echo "Keep Wireless debugging enabled on the Watch."
  echo "If the Watch still trusts this Mac, the background auto-connect will normally restore it."
  echo "Only re-pair if the Watch has actually removed/revoked this Mac."
  "$ADB" devices -l
  exit 1
fi

if [ -n "$LAST_ENDPOINT" ]; then
  printf '%s\n' "$LAST_ENDPOINT" > "$ENDPOINT_FILE"
elif printf '%s' "$TARGET" | grep -Eq '^[0-9.]+:[0-9]+$'; then
  printf '%s\n' "$TARGET" > "$ENDPOINT_FILE"
fi

if [ "$(uname -s)" = "Darwin" ] && [ -f "$HOME/.android/adbkey" ]; then
  mkdir -p "$STATE_DIR/adb-key-backup"
  cp -p "$HOME/.android/adbkey" "$STATE_DIR/adb-key-backup/adbkey"
  [ ! -f "$HOME/.android/adbkey.pub" ] ||
    cp -p "$HOME/.android/adbkey.pub" "$STATE_DIR/adb-key-backup/adbkey.pub"
  chmod 600 "$STATE_DIR/adb-key-backup/adbkey" 2>/dev/null || true
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

INSTALL_APK="$APK"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/raiseai-install.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

if [ "$(uname -s)" = "Darwin" ]; then
  APKSIGNER="$(find "$SDK_DIR/build-tools" -type f -name apksigner 2>/dev/null | sort | tail -n 1)"
  SOURCE_DEBUG_KEY="$HOME/.android/debug.keystore"
  STABLE_KEY="$SIGNING_DIR/raiseai-debug.keystore"

  if [ ! -f "$STABLE_KEY" ] && [ -f "$SOURCE_DEBUG_KEY" ]; then
    cp -p "$SOURCE_DEBUG_KEY" "$STABLE_KEY"
    chmod 600 "$STABLE_KEY"
    echo "Pinned this Mac's existing Android debug key for future Race AI updates."
  fi

  if [ -n "${APKSIGNER:-}" ] && [ -x "$APKSIGNER" ] && [ -f "$STABLE_KEY" ]; then
    SIGNED_APK="$TMP_DIR/RaiseAI-signed.apk"
    "$APKSIGNER" sign       --ks "$STABLE_KEY"       --ks-key-alias androiddebugkey       --ks-pass pass:android       --key-pass pass:android       --out "$SIGNED_APK"       "$APK"
    "$APKSIGNER" verify "$SIGNED_APK"
    INSTALL_APK="$SIGNED_APK"
    echo "APK signed with the pinned Mac Race AI key."
  fi
fi

install_once() {
  "$ADB" -s "$TARGET" install --no-streaming -r "$INSTALL_APK"
}

echo "Installing verified Race AI APK..."
if ! INSTALL_OUTPUT="$(install_once 2>&1)"; then
  printf '%s\n' "$INSTALL_OUTPUT"
  if printf '%s' "$INSTALL_OUTPUT" | grep -q 'INSTALL_FAILED_UPDATE_INCOMPATIBLE'; then
    echo
    echo "Existing Race AI uses a different signing key."
    echo "I will NOT uninstall it automatically because that could erase your ChatGPT session/app data."
    echo "If this Mac built the installed version, make sure ~/.android/debug.keystore still exists."
    exit 1
  fi

  echo "Install failed; trying one automatic reconnect..."
  DISCOVERED_ENDPOINT="$(mdns_endpoint)"
  [ -z "${DISCOVERED_ENDPOINT:-}" ] || connect_endpoint "$DISCOVERED_ENDPOINT" || true
  sleep 1
  TARGET="${ANDROID_SERIAL:-$(find_watch)}"
  [ -n "$TARGET" ] || { echo "Watch did not reconnect."; exit 1; }
  install_once
else
  printf '%s\n' "$INSTALL_OUTPUT"
fi

echo "Applying sideload grants..."
"$ADB" -s "$TARGET" shell appops set "$PACKAGE" SYSTEM_ALERT_WINDOW allow || true
"$ADB" -s "$TARGET" shell appops set "$PACKAGE" GET_USAGE_STATS allow || true

echo "Opening Race AI..."
"$ADB" -s "$TARGET" shell am start -n "$PACKAGE/.MainActivity" >/dev/null

echo
echo "Installed package:"
"$ADB" -s "$TARGET" shell dumpsys package "$PACKAGE" |
  grep -E "versionName=|versionCode=" | head -2

if [ "$(uname -s)" = "Darwin" ] &&
   [ -x "$SCRIPT_DIR/install-mac-adb-autoconnect.command" ] &&
   [ ! -f "$STATE_DIR/autoconnect-installed" ]; then
  "$SCRIPT_DIR/install-mac-adb-autoconnect.command" --quiet || true
fi

echo "Race AI installation complete."