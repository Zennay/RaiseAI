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
BOUND_TARGET="${ANDROID_SERIAL:-}"
if [ -n "$BOUND_TARGET" ]; then
  printf '%s\n' "$DEVICES" | grep -Fxq "$BOUND_TARGET" || {
    echo "Prepared Watch is not connected over ADB: $BOUND_TARGET"
    exit 1
  }
  TARGET="$BOUND_TARGET"
else
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
fi

characteristics="$("$ADB" -s "$TARGET" shell getprop ro.build.characteristics 2>/dev/null | tr -d '\r' || true)"
features="$("$ADB" -s "$TARGET" shell pm list features 2>/dev/null | tr -d '\r' || true)"
if ! printf '%s' "$characteristics" | grep -qi watch &&
   ! printf '%s\n' "$features" | grep -q 'android.hardware.type.watch'; then
  echo "Selected ADB target is not a Wear OS watch: $TARGET"
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
BASE_OUT="${RAISE_OUTPUT_DIR:-$PWD}"
mkdir -p "$BASE_OUT"
OUT="$BASE_OUT/watch-sensor-traces-$STAMP.csv"
TRIALS_OUT="$BASE_OUT/watch-sensor-trials-$STAMP.csv"
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

if "$ADB" -s "$TARGET" shell run-as nl.zennay.raiseai cat files/sensor-trials.csv > "$TRIALS_OUT" 2>/dev/null; then
  if [ -s "$TRIALS_OUT" ]; then
    echo "Saved: $TRIALS_OUT"
  else
    rm -f "$TRIALS_OUT"
  fi
else
  rm -f "$TRIALS_OUT"
fi

if command -v python3 >/dev/null 2>&1; then
  echo "V1 capture progress:"
  python3 tools/analyze-watch-sensor-traces.py "$OUT" || true

  if [ -s "$TRIALS_OUT" ]; then
    echo "V1 detector reliability:"
    python3 tools/analyze-watch-sensor-trials.py "$TRIALS_OUT" || true
    echo "V1 trace/trial pairing:"
    python3 tools/validate-watch-v1-evidence-pair.py "$OUT" "$TRIALS_OUT" || true
  else
    echo "No sensor trial outcomes recorded yet. Install this build and use the Record buttons."
  fi

  if [ "${RAISE_REQUIRE_V1_TRACE_GATE:-0}" = "1" ]; then
    python3 tools/analyze-watch-sensor-traces.py "$OUT" --require-v1-gate
  fi
  if [ "${RAISE_REQUIRE_V1_TRIAL_GATE:-0}" = "1" ]; then
    [ -s "$TRIALS_OUT" ] || { echo "V1 trial gate requested but no trial evidence exists"; exit 1; }
    python3 tools/validate-watch-v1-evidence-pair.py "$OUT" "$TRIALS_OUT"
    python3 tools/analyze-watch-sensor-trials.py "$TRIALS_OUT" --require-v1-gate
  fi
else
  echo "python3 unavailable; Watch CSV evidence was saved but not analyzed"
fi
