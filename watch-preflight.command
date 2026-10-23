#!/bin/bash
set -euo pipefail

if [ "$#" -ne 0 ]; then
  echo "Usage: ./watch-preflight.command"
  exit 2
fi

cd "$(dirname "$0")"
SDK_DIR="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}"
ADB="$SDK_DIR/platform-tools/adb"
[ -x "$ADB" ] || { echo "ADB not found at $ADB"; exit 1; }

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
[ -n "$TARGET" ] || { echo "No connected Wear OS watch found."; "$ADB" devices -l; exit 1; }

echo "Watch: $TARGET"
echo "Model: $($ADB -s "$TARGET" shell getprop ro.product.model | tr -d '\r')"
echo

if "$ADB" -s "$TARGET" shell pm path com.google.android.wearable.assistant 2>/dev/null | grep -q '^package:'; then
  echo "✓ Google/Gemini Wear assistant installed"
else
  echo "○ Google/Gemini Wear assistant package not found"
  exit 1
fi

if "$ADB" -s "$TARGET" shell pm path nl.zennay.raiseai 2>/dev/null | grep -q '^package:'; then
  echo "✓ Raise AI installed"
  echo "Background launch:"
  "$ADB" -s "$TARGET" shell appops get nl.zennay.raiseai SYSTEM_ALERT_WINDOW 2>/dev/null || true
  echo "Gemini foreground guard:"
  "$ADB" -s "$TARGET" shell appops get nl.zennay.raiseai GET_USAGE_STATS 2>/dev/null || true
else
  echo "○ Raise AI not installed"
fi

echo
echo "Testing the exact Google route already verified on this Watch 7…"
"$ADB" -s "$TARGET" shell am start -a android.intent.action.ASSIST -p com.google.android.wearable.assistant

echo
echo "Expected: Gemini opens and immediately listens."
