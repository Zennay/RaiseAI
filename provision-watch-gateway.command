#!/bin/bash
set -euo pipefail

PROFILE="${1:-$HOME/.config/raiseai/watch-gateway.properties}"
PACKAGE="nl.zennay.raiseai"
SDK_DIR="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}"
ADB="$SDK_DIR/platform-tools/adb"

[ -x "$ADB" ] || { echo "adb not found at: $ADB"; exit 1; }
[ -f "$PROFILE" ] || {
  echo "Gateway profile not found: $PROFILE"
  echo "Copy watch-gateway.properties from the VPS first."
  exit 1
}

URL="$(awk -F= '/^url=/{sub(/^[^=]*=/,"");print;exit}' "$PROFILE")"
TOKEN="$(awk -F= '/^token=/{sub(/^[^=]*=/,"");print;exit}' "$PROFILE")"
PIN="$(awk -F= '/^spki_sha256=/{sub(/^[^=]*=/,"");print;exit}' "$PROFILE")"

case "$URL" in
  https://*) ;;
  *) echo "Gateway URL must use HTTPS"; exit 1 ;;
esac

[ "${#TOKEN}" -ge 32 ] || { echo "Gateway token is invalid"; exit 1; }
printf '%s' "$PIN" | grep -Eq '^[0-9a-fA-F]{64}$' || {
  echo "Gateway SPKI pin is invalid"
  exit 1
}

"$ADB" start-server >/dev/null

find_watch() {
  "$ADB" devices -l | awk 'NR>1 && $2=="device" {print $1}' |
  while IFS= read -r serial; do
    [ -z "$serial" ] && continue
    model="$("$ADB" -s "$serial" shell getprop ro.product.model 2>/dev/null | tr -d '\r')"
    features="$("$ADB" -s "$serial" shell pm list features 2>/dev/null | tr -d '\r')"
    if [ "$model" = "SM_L315F" ] ||
       printf '%s\n' "$features" | grep -q 'android.hardware.type.watch'; then
      printf '%s\n' "$serial"
      return 0
    fi
  done
}

TARGET="${ANDROID_SERIAL:-$(find_watch | head -n 1)}"
[ -n "$TARGET" ] || {
  echo "No connected Wear OS watch found."
  echo "Enable Wireless debugging and connect/pair ADB first."
  exit 1
}

"$ADB" devices -l | awk 'NR>1 && $2=="device" {print $1}' | grep -Fxq "$TARGET" || {
  echo "Selected ADB target is not connected: $TARGET"
  exit 1
}

MODEL="$("$ADB" -s "$TARGET" shell getprop ro.product.model 2>/dev/null | tr -d '\r' || true)"
DEVICE="$("$ADB" -s "$TARGET" shell getprop ro.product.device 2>/dev/null | tr -d '\r' || true)"
CHARACTERISTICS="$("$ADB" -s "$TARGET" shell getprop ro.build.characteristics 2>/dev/null | tr -d '\r' || true)"
FEATURES="$("$ADB" -s "$TARGET" shell pm list features 2>/dev/null | tr -d '\r' || true)"
if [ "$MODEL" != "SM_L315F" ] &&
   ! printf '%s' "$DEVICE" | grep -qi '^fresh' &&
   ! printf '%s' "$CHARACTERISTICS" | grep -qi watch &&
   ! printf '%s\n' "$FEATURES" | grep -q 'android.hardware.type.watch'; then
  echo "Refusing gateway provisioning to non-Wear ADB target: $TARGET"
  exit 1
fi

if ! "$ADB" -s "$TARGET" shell run-as "$PACKAGE" id >/dev/null 2>&1; then
  echo "Raise AI debug build is not installed or run-as is unavailable."
  exit 1
fi

TMP="/data/local/tmp/raise-gateway-$$.properties"
cleanup_remote_tmp() {
  "$ADB" -s "$TARGET" shell rm -f "$TMP" >/dev/null 2>&1 || true
}
trap cleanup_remote_tmp EXIT

"$ADB" -s "$TARGET" push "$PROFILE" "$TMP" >/dev/null
"$ADB" -s "$TARGET" shell chmod 600 "$TMP"
"$ADB" -s "$TARGET" shell run-as "$PACKAGE" \
  sh -c "'mkdir -p files && cp $TMP files/raise-gateway.properties && chmod 600 files/raise-gateway.properties'"

cleanup_remote_tmp
trap - EXIT

echo "Gateway profile installed on Watch: $TARGET"
echo "URL: $URL"
echo "SPKI pin verified in profile."
echo "Gateway token was not printed."