#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

PACKAGE="nl.zennay.raiseai"
STATE_DIR="$HOME/.raiseai"
LATEST_SESSION_FILE="$STATE_DIR/latest-physical-validation-session"

usage() {
  cat <<'EOF'
Usage:
  bash ./watch-stability-snapshot.command <label> [session-dir]

Captures read-only Android ApplicationExitInfo evidence for the exact Watch/APK
bound to an existing physical-validation session and analyzes crash/ANR history
at or after that session start.

This command does not restart the app, reboot the Watch, install/update the APK,
clear exit history, or change Raise AI settings.
EOF
}

find_adb() {
  if command -v adb >/dev/null 2>&1; then
    command -v adb
    return
  fi
  for p in \
    "$HOME/Library/Android/sdk/platform-tools/adb" \
    "${ANDROID_HOME:-}/platform-tools/adb" \
    "${ANDROID_SDK_ROOT:-}/platform-tools/adb"; do
    if [ -n "$p" ] && [ -x "$p" ]; then
      printf '%s\n' "$p"
      return
    fi
  done
  return 1
}

json_get() {
  python3 - "$1" "$2" <<'PY'
import json
import sys

path, key = sys.argv[1:3]
with open(path, encoding="utf-8") as handle:
    data = json.load(handle)
value = data.get(key)
if value is None:
    raise SystemExit(2)
print(value)
PY
}

sha256_file() {
  python3 - "$1" <<'PY'
import hashlib
import sys
from pathlib import Path

digest = hashlib.sha256()
with Path(sys.argv[1]).open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
}

label="${1:-}"
case "$label" in
  -h|--help|help)
    usage
    exit 0
    ;;
esac
[ -n "$label" ] || { usage; exit 2; }
case "$label" in
  *[!A-Za-z0-9._-]*)
    echo "Label may contain only letters, numbers, dot, underscore and hyphen." >&2
    exit 2
    ;;
esac

session="${2:-}"
if [ -z "$session" ]; then
  [ -f "$LATEST_SESSION_FILE" ] || {
    echo "No latest physical-validation session found." >&2
    exit 1
  }
  session="$(tr -d '\r\n' < "$LATEST_SESSION_FILE")"
fi
session_json="$session/session.json"
[ -f "$session_json" ] || {
  echo "Missing physical-validation session manifest: $session_json" >&2
  exit 1
}

command -v python3 >/dev/null 2>&1 || {
  echo "Required command not found: python3" >&2
  exit 1
}
[ -f tools/analyze-watch-exit-info.py ] || {
  echo "Missing stability analyzer: tools/analyze-watch-exit-info.py" >&2
  exit 1
}
[ -f tools/verify-watch-apk-identity.py ] || {
  echo "Missing APK identity verifier: tools/verify-watch-apk-identity.py" >&2
  exit 1
}

adb="$(find_adb || true)"
[ -n "$adb" ] || {
  echo "ADB not found." >&2
  exit 1
}

started_at="$(json_get "$session_json" started_at_utc)"
serial="$(json_get "$session_json" watch_serial)"
watch_model="$(json_get "$session_json" watch_model)"
app_version="$(json_get "$session_json" app_version)"
source_revision="$(json_get "$session_json" source_revision | tr 'A-F' 'a-f')"
installed_apk_sha256="$(json_get "$session_json" installed_apk_sha256 | tr 'A-F' 'a-f')"

printf '%s' "$source_revision" | grep -Eq '^[0-9a-f]{40}$' || {
  echo "Session source_revision is invalid." >&2
  exit 1
}
printf '%s' "$installed_apk_sha256" | grep -Eq '^[0-9a-f]{64}$' || {
  echo "Session installed_apk_sha256 is invalid." >&2
  exit 1
}

"$adb" start-server >/dev/null
"$adb" devices | awk 'NR>1 && $2=="device" {print $1}' | grep -Fxq "$serial" || {
  echo "Session Watch is not connected: $serial" >&2
  exit 1
}

actual_model="$("$adb" -s "$serial" shell getprop ro.product.model 2>/dev/null | tr -d '\r' || true)"
characteristics="$("$adb" -s "$serial" shell getprop ro.build.characteristics 2>/dev/null | tr -d '\r' || true)"
features="$("$adb" -s "$serial" shell pm list features 2>/dev/null | tr -d '\r' || true)"
if ! printf '%s' "$characteristics" | grep -qi watch &&
   ! printf '%s\n' "$features" | grep -q 'android.hardware.type.watch'; then
  echo "Session target is no longer identifiable as a Wear OS Watch: $serial" >&2
  exit 1
fi
if [ -n "$watch_model" ] && [ "$actual_model" != "$watch_model" ]; then
  echo "Watch model mismatch: session=$watch_model connected=$actual_model" >&2
  exit 1
fi

installed_version="$("$adb" -s "$serial" shell dumpsys package "$PACKAGE" 2>/dev/null |
  sed -n 's/^[[:space:]]*versionName=//p' | head -n 1 | tr -d '\r')"
[ "$installed_version" = "$app_version" ] || {
  echo "Installed Raise AI version $installed_version does not match session version $app_version" >&2
  exit 1
}

tmp_root="$(mktemp -d "${TMPDIR:-/tmp}/raiseai-stability.XXXXXX")"
cleanup() {
  rm -rf "$tmp_root"
}
trap cleanup EXIT INT TERM

apk_path="$("$adb" -s "$serial" shell pm path "$PACKAGE" 2>/dev/null |
  sed -n 's/^package://p' | head -n 1 | tr -d '\r')"
[ -n "$apk_path" ] || {
  echo "Could not resolve installed Raise AI APK path." >&2
  exit 1
}
installed_apk="$tmp_root/installed.apk"
"$adb" -s "$serial" exec-out cat "$apk_path" > "$installed_apk"
[ -s "$installed_apk" ] || {
  echo "Could not read installed Raise AI APK bytes." >&2
  exit 1
}
actual_apk_sha256="$(sha256_file "$installed_apk" | tr 'A-F' 'a-f')"
[ "$actual_apk_sha256" = "$installed_apk_sha256" ] || {
  echo "Installed on-device APK SHA-256 does not match session identity." >&2
  exit 1
}
python3 tools/verify-watch-apk-identity.py \
  "$installed_apk" \
  --expect-source-revision "$source_revision" \
  --expect-sha256 "$installed_apk_sha256" >/dev/null

raw_output="$session/stability-$label-exit-info.txt"
summary_output="$session/stability-$label.json"
[ ! -e "$raw_output" ] && [ ! -e "$summary_output" ] || {
  echo "Stability evidence already exists for label '$label'." >&2
  exit 1
}

device_utc_offset="$("$adb" -s "$serial" shell date +%z 2>/dev/null | tr -d '\r\n' || true)"
printf '%s' "$device_utc_offset" | grep -Eq '^[+-][0-9]{4}$' || {
  echo "Could not read a valid Watch UTC offset." >&2
  exit 1
}

"$adb" -s "$serial" shell dumpsys activity exit-info "$PACKAGE" > "$raw_output"
grep -Fq "ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)" "$raw_output" || {
  echo "Watch did not return Android ApplicationExitInfo evidence." >&2
  rm -f "$raw_output"
  exit 1
}

services="$("$adb" -s "$serial" shell dumpsys activity services "$PACKAGE" 2>/dev/null | tr -d '\r' || true)"
service_running=false
if printf '%s\n' "$services" | grep -Fq "GestureMonitorService"; then
  service_running=true
fi

set +e
python3 tools/analyze-watch-exit-info.py \
  "$raw_output" \
  --session-start "$started_at" \
  --device-utc-offset "$device_utc_offset" \
  --package "$PACKAGE" \
  --watch-serial "$serial" \
  --watch-model "$watch_model" \
  --app-version "$app_version" \
  --source-revision "$source_revision" \
  --installed-apk-sha256 "$installed_apk_sha256" \
  --service-running "$service_running" \
  --output "$summary_output"
analysis_rc=$?
set -e

if [ "$analysis_rc" -gt 1 ]; then
  echo "Stability evidence could not be analyzed." >&2
  exit "$analysis_rc"
fi

echo "Stability evidence saved:"
echo "  raw:     $raw_output"
echo "  summary: $summary_output"
echo "  Watch:   $serial ($actual_model)"
echo "  Version/source: $app_version / $source_revision"
echo "  Gesture service running: $service_running"

if [ "$analysis_rc" -eq 1 ]; then
  echo "STABILITY FAIL: critical process exit or inactive gesture service detected." >&2
  exit 1
fi

echo "STABILITY PASS: no critical app exit was reported for this session window."
