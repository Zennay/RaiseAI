#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

find_adb() {
  if command -v adb >/dev/null 2>&1; then command -v adb; return; fi
  for p in "$HOME/Library/Android/sdk/platform-tools/adb" "${ANDROID_HOME:-}/platform-tools/adb" "${ANDROID_SDK_ROOT:-}/platform-tools/adb"; do
    if [ -n "$p" ] && [ -x "$p" ]; then echo "$p"; return; fi
  done
  return 1
}
ADB="$(find_adb || true)"
[ -n "$ADB" ] || { echo "ADB not found"; exit 1; }

DEVICES="$($ADB devices | awk 'NR>1 && $2=="device" {print $1}')"
TARGET=""
while IFS= read -r serial; do
  [ -z "$serial" ] && continue
  c="$($ADB -s "$serial" shell getprop ro.build.characteristics 2>/dev/null | tr -d '\r' || true)"
  if printf '%s' "$c" | grep -qi watch; then TARGET="$serial"; break; fi
done <<EOF_DEVICES
$DEVICES
EOF_DEVICES
[ -n "$TARGET" ] || { echo "No ADB Wear OS watch connected"; exit 1; }

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="watch-diagnostics-$STAMP"
mkdir -p "$OUT"

$ADB -s "$TARGET" shell getprop > "$OUT/getprop.txt" || true
$ADB -s "$TARGET" logcat -d -v time RaiseAI.Assistant:V RaiseAI.Gesture:V ActivityTaskManager:W '*:S' > "$OUT/raiseai-logcat.txt" || true
$ADB -s "$TARGET" shell dumpsys package nl.zennay.raiseai > "$OUT/package.txt" || true
$ADB -s "$TARGET" shell appops get nl.zennay.raiseai SYSTEM_ALERT_WINDOW > "$OUT/background-launch-appop.txt" 2>&1 || true
$ADB -s "$TARGET" shell dumpsys activity services nl.zennay.raiseai > "$OUT/services.txt" || true
$ADB -s "$TARGET" shell dumpsys battery > "$OUT/battery.txt" || true
$ADB -s "$TARGET" shell pm path com.google.android.wearable.assistant > "$OUT/google-assistant-package.txt" 2>&1 || true
$ADB -s "$TARGET" exec-out run-as nl.zennay.raiseai cat files/sensor-traces.csv > "$OUT/sensor-traces.csv" 2>/dev/null || true

echo "Saved diagnostics to: $OUT"
