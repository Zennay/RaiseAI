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

if ! "$ADB" -s "$TARGET" shell run-as "$PACKAGE" id >/dev/null 2>&1; then
  echo "Raise AI debug build is not installed or run-as is unavailable."
  exit 1
fi

TMP="/data/local/tmp/raise-gateway.properties"
"$ADB" -s "$TARGET" push "$PROFILE" "$TMP" >/dev/null
"$ADB" -s "$TARGET" shell run-as "$PACKAGE"   sh -c "'mkdir -p files && cp $TMP files/raise-gateway.properties && chmod 600 files/raise-gateway.properties'"
"$ADB" -s "$TARGET" shell rm -f "$TMP"

echo "Gateway profile installed on Watch: $TARGET"
echo "URL: $URL"
echo "SPKI pin verified in profile."
echo "Gateway token was not printed."