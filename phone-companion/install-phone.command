#!/usr/bin/env bash
# Explicit phone-only installer. Shares the Watch package ID for future Wear Data Layer;
# installing a phone build on the Watch would overwrite the Watch app and is forbidden.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
usage() {
  echo "Usage: bash phone-companion/install-phone.command <AUTHORised_ANDROID_PHONE_ADB_SERIAL> [--allow-replace]" >&2
  exit 2
}
[[ "$#" -ge 1 && "$#" -le 2 ]] || usage
serial="$1"
[[ "$serial" =~ ^[A-Za-z0-9._:-]{1,128}$ ]] || usage
[[ "$#" -eq 1 || "$2" == "--allow-replace" ]] || usage
command -v adb >/dev/null || { echo "ADB is required" >&2; exit 1; }

# One explicit, authorized Android phone only. No 'adb install' without -s.
if ! adb devices | awk -v serial="$serial" 'NR>1 && $1 == serial && $2 == "device" {found=1} END {exit !found}'; then
  echo "Selected Android phone is not connected and authorized: $serial" >&2
  exit 1
fi
watch="$(adb -s "$serial" shell pm has-feature android.hardware.type.watch | tr -d '\r')"
if [[ "$watch" != "false" ]]; then
  echo "REFUSED: selected device is Wear OS or device type cannot be verified" >&2
  exit 1
fi

# The phone debug build is a separate module but intentionally uses the *same*
# application ID as the Watch to support a future signature-matched Data Layer.
shopt -s nullglob
apks=("$ROOT"/build/outputs/apk/debug/*.apk)
[[ "${#apks[@]}" -eq 1 ]] || { echo "Expected exactly one built phone companion APK" >&2; exit 1; }
apk="${apks[0]}"
[[ -f "$apk" && ! -L "$apk" ]] || { echo "Unsafe phone APK" >&2; exit 1; }

sdkroot="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
aapt_bin="${RAISE_AAPT:-${sdkroot}/build-tools/35.0.0/aapt}"
[[ -x "$aapt_bin" ]] || { echo "Android SDK 35 aapt is required for APK identity verification" >&2; exit 1; }
badging="$("$aapt_bin" dump badging "$apk")"
printf '%s\n' "$badging" | grep -Fxq "application-label:'Raise AI Phone'" || {
  echo "REFUSED: APK has incorrect phone-only identity label" >&2; exit 1;
}
printf '%s\n' "$badging" | grep -Eq "^package: name='nl[.]zennay[.]raiseai' versionCode='1' versionName='0[.]1[.]0'" || {
  echo "REFUSED: unexpected phone APK application ID/version" >&2; exit 1;
}

existing="$(adb -s "$serial" shell pm path nl.zennay.raiseai | tr -d '\r')"
if [[ "$existing" == package:* && "${2:-}" != "--allow-replace" ]]; then
  echo "REFUSED: this package is already installed on the phone. Re-run with --allow-replace only after checking its data." >&2
  exit 1
fi
adb -s "$serial" install -r "$apk"
echo "Phone-only install requested on serial $serial (NOT on Watch)."
echo "Open Raise AI Phone on the phone, then independently verify the official ChatGPT app publisher certificate."
