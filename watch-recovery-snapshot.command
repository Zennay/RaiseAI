#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

PACKAGE="nl.zennay.raiseai"
STATE_DIR="$HOME/.raiseai"
LATEST_SESSION_FILE="$STATE_DIR/latest-physical-validation-session"

usage() {
  cat <<'EOF'
Usage:
  bash ./watch-recovery-snapshot.command <label> [session-dir]

Captures read-only reboot/update recovery evidence from the exact Watch and APK
bound to an existing physical-validation session. It does not reboot the Watch,
install/update the app, change monitoring state, or mutate device settings.

Examples:
  bash ./watch-recovery-snapshot.command before-reboot
  bash ./watch-recovery-snapshot.command after-reboot ~/.raiseai/evidence/<session>
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
[ -f tools/verify-watch-apk-identity.py ] || {
  echo "Missing APK identity verifier: tools/verify-watch-apk-identity.py" >&2
  exit 1
}

adb="$(find_adb || true)"
[ -n "$adb" ] || {
  echo "ADB not found." >&2
  exit 1
}

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

tmp_root="$(mktemp -d "${TMPDIR:-/tmp}/raiseai-recovery-snapshot.XXXXXX")"
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
  echo "  session: $installed_apk_sha256" >&2
  echo "  device:  $actual_apk_sha256" >&2
  exit 1
}
python3 tools/verify-watch-apk-identity.py \
  "$installed_apk" \
  --expect-source-revision "$source_revision" \
  --expect-sha256 "$installed_apk_sha256" >/dev/null

prefs_xml="$tmp_root/raise_ai_prefs.xml"
if ! "$adb" -s "$serial" exec-out run-as "$PACKAGE" cat shared_prefs/raise_ai_prefs.xml > "$prefs_xml" 2>/dev/null; then
  echo "Could not read Raise AI preferences with run-as." >&2
  exit 1
fi
[ -s "$prefs_xml" ] || {
  echo "Raise AI preferences are empty or missing." >&2
  exit 1
}

prefs_json="$(python3 - "$prefs_xml" <<'PY'
import json
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
values = {}
for node in root:
    name = node.attrib.get("name")
    if not name:
        continue
    if node.tag == "boolean":
        values[name] = node.attrib.get("value", "").lower() == "true"

payload = {
    "monitoring_enabled": values.get("monitoring_enabled", False),
    "calibrated": values.get("calibrated", False),
}
print(json.dumps(payload, separators=(",", ":")))
PY
)"
monitoring_enabled="$(python3 -c 'import json,sys; print(str(json.loads(sys.argv[1])["monitoring_enabled"]).lower())' "$prefs_json")"
calibrated="$(python3 -c 'import json,sys; print(str(json.loads(sys.argv[1])["calibrated"]).lower())' "$prefs_json")"

boot_id="$("$adb" -s "$serial" shell cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n' || true)"
printf '%s' "$boot_id" | grep -Eq '^[0-9a-fA-F-]{36}$' || {
  echo "Could not read a valid Watch boot_id." >&2
  exit 1
}

uptime_raw="$("$adb" -s "$serial" shell cat /proc/uptime 2>/dev/null | tr -d '\r' || true)"
uptime_seconds="$(printf '%s' "$uptime_raw" | awk '{print $1}')"
printf '%s' "$uptime_seconds" | grep -Eq '^[0-9]+([.][0-9]+)?$' || {
  echo "Could not read Watch uptime." >&2
  exit 1
}

services="$("$adb" -s "$serial" shell dumpsys activity services "$PACKAGE" 2>/dev/null | tr -d '\r' || true)"
service_running=false
if printf '%s\n' "$services" | grep -Fq "GestureMonitorService"; then
  service_running=true
fi

output="$session/recovery-$label.json"
[ ! -e "$output" ] || {
  echo "Recovery snapshot already exists for label '$label': $output" >&2
  exit 1
}

TIMESTAMP_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
OUTPUT="$output" LABEL="$label" WATCH_SERIAL="$serial" WATCH_MODEL="$watch_model" \
APP_VERSION="$app_version" SOURCE_REVISION="$source_revision" APK_SHA256="$installed_apk_sha256" \
BOOT_ID="$boot_id" UPTIME_SECONDS="$uptime_seconds" MONITORING_ENABLED="$monitoring_enabled" \
CALIBRATED="$calibrated" SERVICE_RUNNING="$service_running" python3 - <<'PY'
import json
import os
from pathlib import Path

payload = {
    "schema_version": 1,
    "captured_at_utc": os.environ["TIMESTAMP_UTC"],
    "label": os.environ["LABEL"],
    "watch_serial": os.environ["WATCH_SERIAL"],
    "watch_model": os.environ["WATCH_MODEL"],
    "app_version": os.environ["APP_VERSION"],
    "source_revision": os.environ["SOURCE_REVISION"],
    "installed_apk_sha256": os.environ["APK_SHA256"],
    "boot_id": os.environ["BOOT_ID"].lower(),
    "uptime_seconds": float(os.environ["UPTIME_SECONDS"]),
    "monitoring_enabled": os.environ["MONITORING_ENABLED"] == "true",
    "calibrated": os.environ["CALIBRATED"] == "true",
    "gesture_monitor_service_running": os.environ["SERVICE_RUNNING"] == "true",
    "read_only_capture": True,
}
Path(os.environ["OUTPUT"]).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

echo "Recovery evidence snapshot saved:"
echo "  $output"
echo "  Watch: $serial ($actual_model)"
echo "  Version/source: $app_version / $source_revision"
echo "  Boot ID: $boot_id"
echo "  Monitoring enabled: $monitoring_enabled"
echo "  Calibrated: $calibrated"
echo "  Gesture service running: $service_running"
