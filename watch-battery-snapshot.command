#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

STATE_DIR="$HOME/.raiseai"
LATEST_SESSION_FILE="$STATE_DIR/latest-physical-validation-session"

usage() {
  cat <<'EOF'
Usage:
  bash ./watch-battery-snapshot.command <label> [session-dir]

Captures a read-only battery/power snapshot from the exact Watch bound to an
existing physical-validation session. The command never resets batterystats,
changes charging state, or mutates Watch settings.

Examples:
  bash ./watch-battery-snapshot.command before
  bash ./watch-battery-snapshot.command after ~/.raiseai/evidence/20261004T230000Z-v1.5.2-8f719bb273f9
EOF
}

find_adb() {
  if command -v adb >/dev/null 2>&1; then
    command -v adb
    return
  fi
  for p in     "$HOME/Library/Android/sdk/platform-tools/adb"     "${ANDROID_HOME:-}/platform-tools/adb"     "${ANDROID_SDK_ROOT:-}/platform-tools/adb"; do
    if [ -n "$p" ] && [ -x "$p" ]; then
      echo "$p"
      return
    fi
  done
  return 1
}

json_get() {
  local file="$1"
  local key="$2"
  python3 - "$file" "$key" <<'PY'
import json
import sys
path, key = sys.argv[1:3]
data = json.load(open(path, encoding="utf-8"))
value = data.get(key)
if value is None:
    raise SystemExit(2)
print(value)
PY
}

battery_value() {
  local payload="$1"
  local key="$2"
  printf '%s\n' "$payload" |
    sed -n "s/^[[:space:]]*$key:[[:space:]]*//p" |
    head -n 1 |
    tr -d '\r'
}

label="${1:-}"
case "$label" in
  -h|--help)
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
adb="$(find_adb || true)"
[ -n "$adb" ] || {
  echo "ADB not found." >&2
  exit 1
}

serial="$(json_get "$session_json" watch_serial)"
app_version="$(json_get "$session_json" app_version)"
source_revision="$(json_get "$session_json" source_revision)"
watch_model="$(json_get "$session_json" watch_model)"

"$adb" devices | awk 'NR>1 && $2=="device" {print $1}' | grep -Fxq "$serial" || {
  echo "Session Watch is not connected: $serial" >&2
  exit 1
}

actual_model="$("$adb" -s "$serial" shell getprop ro.product.model 2>/dev/null | tr -d '\r' || true)"
characteristics="$("$adb" -s "$serial" shell getprop ro.build.characteristics 2>/dev/null | tr -d '\r' || true)"
features="$("$adb" -s "$serial" shell pm list features 2>/dev/null | tr -d '\r' || true)"
if [ "$actual_model" != "SM_L315F" ] &&
   ! printf '%s' "$characteristics" | grep -qi watch &&
   ! printf '%s\n' "$features" | grep -q 'android.hardware.type.watch'; then
  echo "Session target is no longer identifiable as a Wear OS Watch: $serial" >&2
  exit 1
fi

installed_version="$("$adb" -s "$serial" shell dumpsys package nl.zennay.raiseai 2>/dev/null |
  sed -n 's/^[[:space:]]*versionName=//p' | head -n 1 | tr -d '\r')"
[ "$installed_version" = "$app_version" ] || {
  echo "Installed Raise AI version $installed_version does not match session version $app_version" >&2
  exit 1
}

battery="$("$adb" -s "$serial" shell dumpsys battery 2>/dev/null | tr -d '\r')"
level="$(battery_value "$battery" level)"
scale="$(battery_value "$battery" scale)"
status="$(battery_value "$battery" status)"
plugged="$(battery_value "$battery" plugged)"
temperature_tenths_c="$(battery_value "$battery" temperature)"
voltage_mv="$(battery_value "$battery" voltage)"
health="$(battery_value "$battery" health)"
present="$(battery_value "$battery" present)"
technology="$(battery_value "$battery" technology)"

for pair in "level:$level" "scale:$scale" "status:$status" "plugged:$plugged"; do
  name="${pair%%:*}"
  value="${pair#*:}"
  printf '%s' "$value" | grep -Eq '^[0-9]+$' || {
    echo "Could not parse numeric battery field $name from dumpsys battery." >&2
    exit 1
  }
done
[ "$scale" -gt 0 ] || {
  echo "Battery scale must be greater than zero." >&2
  exit 1
}

uptime_raw="$("$adb" -s "$serial" shell cat /proc/uptime 2>/dev/null | tr -d '\r' || true)"
uptime_seconds="$(printf '%s' "$uptime_raw" | awk '{print $1}')"
printf '%s' "$uptime_seconds" | grep -Eq '^[0-9]+([.][0-9]+)?$' || uptime_seconds=""

wakefulness="$("$adb" -s "$serial" shell dumpsys power 2>/dev/null |
  sed -n 's/^[[:space:]]*mWakefulness=//p' | head -n 1 | tr -d '\r' || true)"

output="$session/battery-$label.json"
[ ! -e "$output" ] || {
  echo "Battery snapshot already exists for label '$label': $output" >&2
  exit 1
}

TIMESTAMP_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)" OUTPUT="$output" LABEL="$label" WATCH_SERIAL="$serial" WATCH_MODEL="$watch_model" ACTUAL_MODEL="$actual_model" APP_VERSION="$app_version" SOURCE_REVISION="$source_revision" LEVEL="$level" SCALE="$scale" STATUS="$status" PLUGGED="$plugged" TEMPERATURE_TENTHS_C="$temperature_tenths_c" VOLTAGE_MV="$voltage_mv" HEALTH="$health" PRESENT="$present" TECHNOLOGY="$technology" UPTIME_SECONDS="$uptime_seconds" WAKEFULNESS="$wakefulness" python3 - <<'PY'
import json
import os
from pathlib import Path

def optional_int(name):
    value = os.environ.get(name, "").strip()
    try:
        return int(value)
    except ValueError:
        return None

level = int(os.environ["LEVEL"])
scale = int(os.environ["SCALE"])
payload = {
    "schema_version": 1,
    "captured_at_utc": os.environ["TIMESTAMP_UTC"],
    "label": os.environ["LABEL"],
    "watch_serial": os.environ["WATCH_SERIAL"],
    "watch_model": os.environ["WATCH_MODEL"],
    "reported_watch_model": os.environ["ACTUAL_MODEL"],
    "app_version": os.environ["APP_VERSION"],
    "source_revision": os.environ["SOURCE_REVISION"],
    "battery_level": level,
    "battery_scale": scale,
    "battery_percent": round(level * 100.0 / scale, 3),
    "battery_status": int(os.environ["STATUS"]),
    "plugged": int(os.environ["PLUGGED"]),
    "temperature_c": (
        optional_int("TEMPERATURE_TENTHS_C") / 10.0
        if optional_int("TEMPERATURE_TENTHS_C") is not None
        else None
    ),
    "voltage_mv": optional_int("VOLTAGE_MV"),
    "health": optional_int("HEALTH"),
    "present": os.environ.get("PRESENT", "").strip().lower() == "true",
    "technology": os.environ.get("TECHNOLOGY", "").strip() or None,
    "uptime_seconds": (
        float(os.environ["UPTIME_SECONDS"])
        if os.environ.get("UPTIME_SECONDS")
        else None
    ),
    "wakefulness": os.environ.get("WAKEFULNESS", "").strip() or None,
    "read_only_capture": True,
}
Path(os.environ["OUTPUT"]).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

echo "Battery evidence snapshot saved:"
echo "  $output"
echo "  Watch: $serial ($actual_model)"
python3 - "$output" <<'PY'
import json
import sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
print(f"  Battery: {data['battery_percent']:.1f}%")
print(f"  Plugged: {data['plugged']}")
print(f"  Wakefulness: {data.get('wakefulness') or 'unknown'}")
PY
