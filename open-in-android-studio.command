#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
cd "$SCRIPT_DIR"

if [ "$#" -ne 0 ]; then
  echo "Usage: ./open-in-android-studio.command"
  exit 2
fi

ANDROID_STUDIO_APP="/Applications/Android Studio.app"

if [ -d "$ANDROID_STUDIO_APP" ]; then
  exec open -a "$ANDROID_STUDIO_APP" "$SCRIPT_DIR"
fi

echo "Android Studio was not found in /Applications."
echo "Install Android Studio, then double-click this file again."
if [ -t 0 ]; then
  read -r -p "Press Enter to close…" _ || true
fi
exit 1
