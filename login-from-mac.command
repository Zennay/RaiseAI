#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

find_adb() {
  if command -v adb >/dev/null 2>&1; then
    command -v adb
    return
  fi

  for candidate in     "$HOME/Library/Android/sdk/platform-tools/adb"     "$HOME/Android/Sdk/platform-tools/adb"; do
    if [ -x "$candidate" ]; then
      echo "$candidate"
      return
    fi
  done

  return 1
}

ADB="$(find_adb || true)"
if [ -z "$ADB" ]; then
  echo "ADB niet gevonden. Installeer Android platform-tools of open eerst Android Studio."
  exit 1
fi

mapfile_devices() {
  "$ADB" devices | awk 'NR > 1 && $2 == "device" {print $1}'
}

WATCHES=()
while IFS= read -r serial; do
  [ -n "$serial" ] || continue
  characteristics="$("$ADB" -s "$serial" shell getprop ro.build.characteristics 2>/dev/null | tr -d '\r' || true)"
  model="$("$ADB" -s "$serial" shell getprop ro.product.model 2>/dev/null | tr -d '\r' || true)"
  if echo "$characteristics" | grep -qi "watch"; then
    case "$model" in
      SM-L315F|SM_L315F)
        WATCHES+=("$serial")
        ;;
    esac
  fi
done < <(mapfile_devices)

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
    echo "Meerdere Galaxy Watch 7-apparaten gevonden. Verbind precies één Watch voordat je de login opent."
    exit 1
    ;;
esac

echo "Watch gevonden: $WATCH"

"$ADB" -s "$WATCH" shell am start   -n nl.zennay.raiseai/.MainActivity   --ez open_chatgpt_login true >/dev/null

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
