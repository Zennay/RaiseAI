#!/bin/bash
set -euo pipefail

if [ "$#" -ne 0 ]; then
  echo "Usage: ./login-from-mac.command"
  exit 2
fi

find_adb() {
  if command -v adb >/dev/null 2>&1; then
    candidate="$(command -v adb)"
    if [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi

  for candidate in \
    "$HOME/Library/Android/sdk/platform-tools/adb" \
    "$HOME/Android/Sdk/platform-tools/adb"; do
    if [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

ADB="$(find_adb || true)"
if [ -z "$ADB" ]; then
  echo "ADB niet gevonden. Installeer Android platform-tools of open eerst Android Studio."
  exit 1
fi

devices_output=""
if ! devices_output="$("$ADB" devices 2>&1)"; then
  echo "ADB device enumeration failed."
  printf '%s\n' "$devices_output"
  exit 1
fi

connected_devices="$(
  printf '%s\n' "$devices_output" |
    awk 'NR > 1 && $2 == "device" {print $1}'
)"

is_expected_watch() {
  local serial="$1"
  local characteristics model normalized_characteristics

  if ! characteristics="$("$ADB" -s "$serial" shell getprop ro.build.characteristics 2>/dev/null | tr -d '\r')"; then
    return 1
  fi
  if ! model="$("$ADB" -s "$serial" shell getprop ro.product.model 2>/dev/null | tr -d '\r')"; then
    return 1
  fi

  normalized_characteristics="$(printf '%s' "$characteristics" | tr '[:upper:]' '[:lower:]')"
  case "$normalized_characteristics" in
    *watch*) ;;
    *) return 1 ;;
  esac

  case "$model" in
    SM-L315F|SM_L315F) return 0 ;;
    *) return 1 ;;
  esac
}

BOUND_TARGET="${ANDROID_SERIAL:-}"
if [ -n "$BOUND_TARGET" ]; then
  printf '%s\n' "$connected_devices" | grep -Fxq "$BOUND_TARGET" || {
    echo "Prepared Galaxy Watch 7 is not connected over ADB: $BOUND_TARGET"
    exit 1
  }
  is_expected_watch "$BOUND_TARGET" || {
    echo "Prepared ADB target is not the expected Galaxy Watch 7 (SM-L315F): $BOUND_TARGET"
    exit 1
  }
  WATCH="$BOUND_TARGET"
else
  WATCHES=()
  while IFS= read -r serial; do
    [ -n "$serial" ] || continue
    if is_expected_watch "$serial"; then
      WATCHES+=("$serial")
    fi
  done < <(printf '%s\n' "$connected_devices")

  case "${#WATCHES[@]}" in
    0)
      echo "Geen verbonden Galaxy Watch 7 (SM-L315F) gevonden."
      echo "Zet Wireless debugging aan en verbind eerst met: adb connect WATCH_IP:PORT"
      exit 1
      ;;
    1)
      WATCH="${WATCHES[0]}"
      ;;
    *)
      echo "Meerdere Galaxy Watch 7-apparaten gevonden. Verbind precies één Watch of stel ANDROID_SERIAL expliciet in."
      exit 1
      ;;
  esac
fi

if ! "$ADB" -s "$WATCH" get-state >/dev/null 2>&1; then
  echo "Galaxy Watch 7 is niet meer bereikbaar over ADB: $WATCH"
  exit 1
fi

echo "Watch gevonden: $WATCH"

if ! "$ADB" -s "$WATCH" shell am start \
  -n nl.zennay.raiseai/.MainActivity \
  --ez open_chatgpt_login true >/dev/null; then
  echo "Kon Raise AI login niet openen op Watch: $WATCH"
  exit 1
fi

if command -v scrcpy >/dev/null 2>&1; then
  echo "Raise AI opent op de Watch. Log nu in via het scrcpy-venster op je Mac."
  echo "Je login en cookies blijven op de Watch; Raise AI kopieert ze niet naar een server."
  exec scrcpy -s "$WATCH" --window-title "Raise AI · Watch login"
fi

echo
echo "Raise AI is op de Watch geopend."
echo "Voor bediening met je Mac-toetsenbord installeer scrcpy:"
echo "  brew install scrcpy"
echo "Start daarna dit script opnieuw."
echo
echo "Je kunt ook Android Studio Device Mirroring gebruiken."
