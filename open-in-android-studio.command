#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ -d "/Applications/Android Studio.app" ]; then
  open -a "Android Studio" "$PWD"
else
  echo "Android Studio was not found in /Applications."
  echo "Install Android Studio, then double-click this file again."
  read -r -p "Press Enter to close…" _
fi
