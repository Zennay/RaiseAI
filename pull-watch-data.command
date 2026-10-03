#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

find_adb() {
  if command -v adb >/dev/null 2>&1; then command -v adb; return; fi
  for p in \
    "$HOME/Library/Android/sdk/platform-tools/adb" \
    "${ANDROID_HOME:-}/platform-tools/adb" \
    "${ANDROID_SDK_ROOT:-}/platform-tools/adb"; do
    if [ -n "$p" ] && [ -x "$p" ]; then echo "$p"; return; fi
  done
  return 1
}

ADB="$(find_adb || true)"
if [ -z "$ADB" ]; then
  echo "ADB not found. Open Android Studio and install Android SDK Platform-Tools."
  exit 1
fi

DEVICES="$("$ADB" devices | awk 'NR>1 && $2=="device" {print $1}')"
COUNT="$(printf '%s\n' "$DEVICES" | awk 'NF {n++} END {print n+0}')"
if [ "$COUNT" -eq 0 ]; then
  echo "No watch connected over ADB. Turn on Wireless debugging and connect first."
  exit 1
elif [ "$COUNT" -eq 1 ]; then
  TARGET="$(printf '%s\n' "$DEVICES" | awk 'NF {print; exit}')"
else
  echo "Connected devices:"
  printf '%s\n' "$DEVICES" | sed 's/^/  /'
  read -r -p "Watch serial/address: " TARGET
fi

OUT="$PWD/watch-sensor-traces-$(date +%Y%m%d-%H%M%S).csv"
if "$ADB" -s "$TARGET" shell run-as nl.zennay.raiseai cat files/sensor-traces.csv > "$OUT" 2>/dev/null; then
  if [ -s "$OUT" ]; then
    echo "Saved: $OUT"
  else
    rm -f "$OUT"
    echo "No sensor samples recorded yet. Use a Record button in Raise AI first."
    exit 1
  fi
else
  rm -f "$OUT"
  echo "Could not read debug app data. Make sure the debug build is installed and the watch is connected."
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  echo "V1 reliability evidence progress:"
  python3 tools/analyze-watch-sensor-traces.py "$OUT" || true
  if [ "${RAISE_REQUIRE_V1_TRACE_GATE:-0}" = "1" ]; then
    python3 tools/analyze-watch-sensor-traces.py "$OUT" --require-v1-gate
  fi
else
  echo "python3 unavailable; trace CSV saved but V1 readiness was not analyzed"
fi
