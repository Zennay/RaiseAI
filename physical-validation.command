#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

PACKAGE="nl.zennay.raiseai"
STATE_DIR="$HOME/.raiseai"
EVIDENCE_ROOT="${RAISE_EVIDENCE_ROOT:-$STATE_DIR/evidence}"
LATEST_SESSION_FILE="$STATE_DIR/latest-physical-validation-session"
DEFAULT_PROFILE="$HOME/.config/raiseai/watch-gateway.properties"

mkdir -p "$STATE_DIR" "$EVIDENCE_ROOT"

usage() {
  cat <<'EOF'
Usage:
  bash ./physical-validation.command prepare [gateway-profile]
  bash ./physical-validation.command verify-e2e [session-dir]
  bash ./physical-validation.command verify-v1 [session-dir]
  bash ./physical-validation.command status [session-dir]
  bash ./physical-validation.command all [gateway-profile]

prepare:
  Builds/installs the exact clean Git revision, provisions the gateway profile,
  clears only prior test evidence, and opens Raise AI. Set RAISE_PREBUILT_APK
  to install an already-published APK instead of rebuilding it; optionally set
  RAISE_EXPECT_APK_SHA256 to bind that APK to a handoff manifest.

verify-e2e:
  Pulls fresh Watch diagnostics and requires a quick_ai answer from the exact
  app version + source revision prepared for this session.

verify-v1:
  Requires the E2E gate to have passed, then exports and scores the physical
  30 raise / 100 non-trigger reliability dataset.

all:
  Runs prepare, pauses for the manual Watch E2E interaction, verifies it,
  pauses for the manual 30/100 gesture session, then verifies V1.
EOF
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1"
    exit 1
  }
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

find_watch() {
  local adb="$1"
  local serial model characteristics features
  "$adb" devices -l | awk 'NR>1 && $2=="device" {print $1}' |
  while IFS= read -r serial; do
    [ -n "$serial" ] || continue
    model="$("$adb" -s "$serial" shell getprop ro.product.model 2>/dev/null | tr -d '\r' || true)"
    characteristics="$("$adb" -s "$serial" shell getprop ro.build.characteristics 2>/dev/null | tr -d '\r' || true)"
    features="$("$adb" -s "$serial" shell pm list features 2>/dev/null | tr -d '\r' || true)"
    if [ "$model" = "SM_L315F" ] ||
       printf '%s' "$characteristics" | grep -qi watch ||
       printf '%s\n' "$features" | grep -q 'android.hardware.type.watch'; then
      printf '%s\n' "$serial"
      return 0
    fi
  done
}

resolve_session() {
  local requested="${1:-}"
  if [ -n "$requested" ]; then
    printf '%s\n' "$requested"
    return
  fi
  [ -f "$LATEST_SESSION_FILE" ] || {
    echo "No previous physical validation session found." >&2
    echo "Run: bash ./physical-validation.command prepare [gateway-profile]" >&2
    return 1
  }
  tr -d '\r\n' < "$LATEST_SESSION_FILE"
}

json_get() {
  local file="$1"
  local key="$2"
  python3 - "$file" "$key" <<'PY'
import json
import sys
path, key = sys.argv[1], sys.argv[2]
data = json.load(open(path, encoding="utf-8"))
value = data.get(key)
if value is None:
    raise SystemExit(2)
if isinstance(value, bool):
    print("true" if value else "false")
else:
    print(value)
PY
}

json_set() {
  local file="$1"
  local key="$2"
  local value="$3"
  python3 - "$file" "$key" "$value" <<'PY'
import json
import sys
path, key, value = sys.argv[1:4]
with open(path, encoding="utf-8") as handle:
    data = json.load(handle)
if value == "true":
    parsed = True
elif value == "false":
    parsed = False
else:
    parsed = value
data[key] = parsed
with open(path, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
}

prepare_session() {
  local profile="${1:-${RAISE_GATEWAY_PROFILE:-$DEFAULT_PROFILE}}"
  require_command git
  require_command python3

  [ -f "$profile" ] || {
    echo "Gateway profile not found: $profile"
    exit 1
  }

  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
    echo "Physical validation must run from a Git checkout."
    exit 1
  }
  if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
    echo "Refusing physical validation from a dirty worktree."
    echo "Commit/stash changes and use the exact source revision you want to prove."
    exit 1
  fi

  local revision version gradle_version stamp session adb target model installed_version
  local prebuilt_apk expected_apk_sha selected_apk install_mode apk_sha
  local -a verify_args
  revision="$(git rev-parse HEAD | tr 'A-F' 'a-f')"
  printf '%s' "$revision" | grep -Eq '^[0-9a-f]{40}$' || {
    echo "Could not resolve a full Git revision."
    exit 1
  }

  version="$(tr -d '\r\n' < VERSION.txt)"
  gradle_version="$(sed -n 's/.*versionName = "\([^"]*\)".*/\1/p' app/build.gradle.kts | head -n 1)"
  [ "$version" = "$gradle_version" ] || {
    echo "Version mismatch: VERSION.txt=$version, Gradle=$gradle_version"
    exit 1
  }

  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  session="$EVIDENCE_ROOT/${stamp}-v${version}-${revision:0:12}"
  mkdir -p "$session"

  echo "Preparing physical validation session:"
  echo "  version:  $version"
  echo "  revision: $revision"
  echo "  evidence: $session"

  prebuilt_apk="${RAISE_PREBUILT_APK:-}"
  expected_apk_sha="${RAISE_EXPECT_APK_SHA256:-}"
  if [ -n "$prebuilt_apk" ]; then
    [ -f "$prebuilt_apk" ] || {
      echo "Prebuilt APK not found: $prebuilt_apk"
      exit 1
    }
    verify_args=(
      python3 tools/verify-watch-apk-identity.py
      "$prebuilt_apk"
      --expect-source-revision "$revision"
    )
    if [ -n "$expected_apk_sha" ]; then
      verify_args+=(--expect-sha256 "$expected_apk_sha")
    fi
    "${verify_args[@]}" | tee "$session/apk-verification.json"
    bash ./install-watch-apk.command "$prebuilt_apk"
    selected_apk="$prebuilt_apk"
    install_mode="prebuilt_apk"
  else
    RAISE_BUILD_REVISION="$revision" bash ./upgrade-watch.command
    selected_apk="app/build/outputs/apk/debug/app-debug.apk"
    python3 tools/verify-watch-apk-identity.py       "$selected_apk"       --expect-source-revision "$revision" | tee "$session/apk-verification.json"
    install_mode="source_build"
  fi

  apk_sha="$(python3 - "$selected_apk" <<'PY'
import hashlib
import sys
from pathlib import Path
path = Path(sys.argv[1])
print(hashlib.sha256(path.read_bytes()).hexdigest())
PY
)"
  printf '%s' "$apk_sha" | grep -Eq '^[0-9a-f]{64}  [ -n "$adb" ] || { echo "ADB not found after install"; exit 1; }
  target="${ANDROID_SERIAL:-$(find_watch "$adb" | head -n 1)}"
  [ -n "$target" ] || { echo "Watch disconnected after install"; exit 1; }

  model="$("$adb" -s "$target" shell getprop ro.product.model | tr -d '\r')"
  installed_version="$("$adb" -s "$target" shell dumpsys package "$PACKAGE" |
    sed -n 's/^[[:space:]]*versionName=//p' | head -n 1 | tr -d '\r')"
  [ "$installed_version" = "$version" ] || {
    echo "Installed Watch version $installed_version does not match prepared version $version"
    exit 1
  }

  echo "Clearing prior validation evidence only..."
  "$adb" -s "$target" shell run-as "$PACKAGE" sh -c     "'rm -f files/watch-e2e-evidence.json files/sensor-traces.csv files/sensor-trials.csv'"
  "$adb" -s "$target" logcat -c || true
  "$adb" -s "$target" shell am start -n "$PACKAGE/.MainActivity" >/dev/null

  STARTED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"   SESSION_PATH="$session"   APP_VERSION="$version"   SOURCE_REVISION="$revision"   WATCH_MODEL="$model"   INSTALL_MODE="$install_mode"   APK_SHA256="$apk_sha"   python3 - <<'PY'
import json
import os
from pathlib import Path
session = Path(os.environ["SESSION_PATH"])
payload = {
    "schema_version": 1,
    "started_at_utc": os.environ["STARTED_AT_UTC"],
    "app_version": os.environ["APP_VERSION"],
    "source_revision": os.environ["SOURCE_REVISION"],
    "watch_model": os.environ["WATCH_MODEL"],
    "install_mode": os.environ["INSTALL_MODE"],
    "apk_sha256": os.environ["APK_SHA256"],
    "e2e_passed": False,
    "v1_gate_passed": False,
}
(session / "session.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

  printf '%s\n' "$session" > "$LATEST_SESSION_FILE"
  echo
  echo "PREPARE PASS"
  echo "On the Watch: open Native Raise AI and complete one short normal AI question."
  echo "Immediately afterwards run:"
  echo "  bash ./physical-validation.command verify-e2e '$session'"
  printf '%s\n' "$session"
}

verify_e2e() {
  local session
  session="$(resolve_session "${1:-}")"
  [ -f "$session/session.json" ] || { echo "Invalid session: $session"; exit 1; }
  require_command python3

  local version revision
  version="$(json_get "$session/session.json" app_version)"
  revision="$(json_get "$session/session.json" source_revision)"

  RAISE_OUTPUT_DIR="$session"   RAISE_E2E_EXPECT_APP_VERSION="$version"   RAISE_E2E_EXPECT_SOURCE_REVISION="$revision"     bash ./pull-diagnostics.command

  local diag evidence result
  diag="$(find "$session" -maxdepth 1 -type d -name 'watch-diagnostics-*' -print | sort | tail -n 1)"
  [ -n "$diag" ] || { echo "No diagnostics directory produced"; exit 1; }
  evidence="$diag/watch-e2e-evidence.json"
  [ -s "$evidence" ] || {
    echo "No fresh Watch E2E evidence found."
    echo "Complete a native Watch AI request and retry immediately."
    exit 1
  }

  result="$session/e2e-result.json"
  python3 tools/validate-watch-e2e-evidence.py     "$evidence"     --expect-route quick_ai     --max-latency-ms 15000     --max-age-seconds 300     --require-answer     --expect-app-version "$version"     --expect-source-revision "$revision" | tee "$result"

  json_set "$session/session.json" e2e_passed true
  json_set "$session/session.json" e2e_verified_at_utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "E2E PASS — exact Watch build ${version} @ ${revision}"
  echo "Next: collect at least 30 mouth raises and 100 representative non-trigger trials."
  echo "Then run:"
  echo "  bash ./physical-validation.command verify-v1 '$session'"
}

verify_v1() {
  local session
  session="$(resolve_session "${1:-}")"
  [ -f "$session/session.json" ] || { echo "Invalid session: $session"; exit 1; }
  require_command python3

  local e2e_passed version revision
  e2e_passed="$(json_get "$session/session.json" e2e_passed)"
  [ "$e2e_passed" = "true" ] || {
    echo "Refusing V1 gate before this session's fresh E2E gate has passed."
    echo "Run verify-e2e first."
    exit 1
  }
  version="$(json_get "$session/session.json" app_version)"
  revision="$(json_get "$session/session.json" source_revision)"

  RAISE_OUTPUT_DIR="$session"   RAISE_REQUIRE_V1_TRACE_GATE=1   RAISE_REQUIRE_V1_TRIAL_GATE=1     bash ./pull-watch-data.command

  local trials result
  trials="$(find "$session" -maxdepth 1 -type f -name 'watch-sensor-trials-*.csv' -print | sort | tail -n 1)"
  [ -n "$trials" ] || { echo "No trial evidence was exported"; exit 1; }

  result="$session/v1-result.json"
  python3 tools/analyze-watch-sensor-trials.py "$trials" \
    --expect-app-version "$version" \
    --expect-source-revision "$revision" \
    --require-v1-gate | tee "$result"

  json_set "$session/session.json" v1_gate_passed true
  json_set "$session/session.json" v1_verified_at_utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "V1 RELIABILITY PASS"
  echo "Evidence directory: $session"
}

show_status() {
  local session
  session="$(resolve_session "${1:-}")"
  [ -f "$session/session.json" ] || { echo "Invalid session: $session"; exit 1; }
  cat "$session/session.json"

  local trials
  trials="$(find "$session" -maxdepth 1 -type f -name 'watch-sensor-trials-*.csv' -print | sort | tail -n 1)"
  if [ -n "$trials" ] && command -v python3 >/dev/null 2>&1; then
    echo
    echo "Latest V1 trial score:"
    python3 tools/analyze-watch-sensor-trials.py "$trials" || true
  fi
}

run_all() {
  local profile="${1:-${RAISE_GATEWAY_PROFILE:-$DEFAULT_PROFILE}}"
  local session
  prepare_session "$profile"
  session="$(resolve_session)"

  echo
  read -r -p "Complete one short Native Raise AI question on the Watch, then press Enter to verify E2E. " _
  verify_e2e "$session"

  echo
  read -r -p "Collect 30 mouth raises + 100 non-trigger trials, then press Enter to verify V1. " _
  verify_v1 "$session"
}

case "${1:-}" in
  prepare)
    prepare_session "${2:-}"
    ;;
  verify-e2e)
    verify_e2e "${2:-}"
    ;;
  verify-v1)
    verify_v1 "${2:-}"
    ;;
  status)
    show_status "${2:-}"
    ;;
  all)
    run_all "${2:-}"
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "Unknown command: $1"
    usage
    exit 2
    ;;
esac
 || {
    echo "Could not compute APK SHA-256."
    exit 1
  }

  bash ./provision-watch-gateway.command "$profile"

  adb="$(find_adb || true)"
  [ -n "$adb" ] || { echo "ADB not found after install"; exit 1; }
  target="${ANDROID_SERIAL:-$(find_watch "$adb" | head -n 1)}"
  [ -n "$target" ] || { echo "Watch disconnected after install"; exit 1; }

  model="$("$adb" -s "$target" shell getprop ro.product.model | tr -d '\r')"
  installed_version="$("$adb" -s "$target" shell dumpsys package "$PACKAGE" |
    sed -n 's/^[[:space:]]*versionName=//p' | head -n 1 | tr -d '\r')"
  [ "$installed_version" = "$version" ] || {
    echo "Installed Watch version $installed_version does not match prepared version $version"
    exit 1
  }

  echo "Clearing prior validation evidence only..."
  "$adb" -s "$target" shell run-as "$PACKAGE" sh -c     "'rm -f files/watch-e2e-evidence.json files/sensor-traces.csv files/sensor-trials.csv'"
  "$adb" -s "$target" logcat -c || true
  "$adb" -s "$target" shell am start -n "$PACKAGE/.MainActivity" >/dev/null

  STARTED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"   SESSION_PATH="$session"   APP_VERSION="$version"   SOURCE_REVISION="$revision"   WATCH_MODEL="$model"   python3 - <<'PY'
import json
import os
from pathlib import Path
session = Path(os.environ["SESSION_PATH"])
payload = {
    "schema_version": 1,
    "started_at_utc": os.environ["STARTED_AT_UTC"],
    "app_version": os.environ["APP_VERSION"],
    "source_revision": os.environ["SOURCE_REVISION"],
    "watch_model": os.environ["WATCH_MODEL"],
    "e2e_passed": False,
    "v1_gate_passed": False,
}
(session / "session.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

  printf '%s\n' "$session" > "$LATEST_SESSION_FILE"
  echo
  echo "PREPARE PASS"
  echo "On the Watch: open Native Raise AI and complete one short normal AI question."
  echo "Immediately afterwards run:"
  echo "  bash ./physical-validation.command verify-e2e '$session'"
  printf '%s\n' "$session"
}

verify_e2e() {
  local session
  session="$(resolve_session "${1:-}")"
  [ -f "$session/session.json" ] || { echo "Invalid session: $session"; exit 1; }
  require_command python3

  local version revision
  version="$(json_get "$session/session.json" app_version)"
  revision="$(json_get "$session/session.json" source_revision)"

  RAISE_OUTPUT_DIR="$session"   RAISE_E2E_EXPECT_APP_VERSION="$version"   RAISE_E2E_EXPECT_SOURCE_REVISION="$revision"     bash ./pull-diagnostics.command

  local diag evidence result
  diag="$(find "$session" -maxdepth 1 -type d -name 'watch-diagnostics-*' -print | sort | tail -n 1)"
  [ -n "$diag" ] || { echo "No diagnostics directory produced"; exit 1; }
  evidence="$diag/watch-e2e-evidence.json"
  [ -s "$evidence" ] || {
    echo "No fresh Watch E2E evidence found."
    echo "Complete a native Watch AI request and retry immediately."
    exit 1
  }

  result="$session/e2e-result.json"
  python3 tools/validate-watch-e2e-evidence.py     "$evidence"     --expect-route quick_ai     --max-latency-ms 15000     --max-age-seconds 300     --require-answer     --expect-app-version "$version"     --expect-source-revision "$revision" | tee "$result"

  json_set "$session/session.json" e2e_passed true
  json_set "$session/session.json" e2e_verified_at_utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "E2E PASS — exact Watch build ${version} @ ${revision}"
  echo "Next: collect at least 30 mouth raises and 100 representative non-trigger trials."
  echo "Then run:"
  echo "  bash ./physical-validation.command verify-v1 '$session'"
}

verify_v1() {
  local session
  session="$(resolve_session "${1:-}")"
  [ -f "$session/session.json" ] || { echo "Invalid session: $session"; exit 1; }
  require_command python3

  local e2e_passed version revision
  e2e_passed="$(json_get "$session/session.json" e2e_passed)"
  [ "$e2e_passed" = "true" ] || {
    echo "Refusing V1 gate before this session's fresh E2E gate has passed."
    echo "Run verify-e2e first."
    exit 1
  }
  version="$(json_get "$session/session.json" app_version)"
  revision="$(json_get "$session/session.json" source_revision)"

  RAISE_OUTPUT_DIR="$session"   RAISE_REQUIRE_V1_TRACE_GATE=1   RAISE_REQUIRE_V1_TRIAL_GATE=1     bash ./pull-watch-data.command

  local trials result
  trials="$(find "$session" -maxdepth 1 -type f -name 'watch-sensor-trials-*.csv' -print | sort | tail -n 1)"
  [ -n "$trials" ] || { echo "No trial evidence was exported"; exit 1; }

  result="$session/v1-result.json"
  python3 tools/analyze-watch-sensor-trials.py "$trials" \
    --expect-app-version "$version" \
    --expect-source-revision "$revision" \
    --require-v1-gate | tee "$result"

  json_set "$session/session.json" v1_gate_passed true
  json_set "$session/session.json" v1_verified_at_utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "V1 RELIABILITY PASS"
  echo "Evidence directory: $session"
}

show_status() {
  local session
  session="$(resolve_session "${1:-}")"
  [ -f "$session/session.json" ] || { echo "Invalid session: $session"; exit 1; }
  cat "$session/session.json"

  local trials
  trials="$(find "$session" -maxdepth 1 -type f -name 'watch-sensor-trials-*.csv' -print | sort | tail -n 1)"
  if [ -n "$trials" ] && command -v python3 >/dev/null 2>&1; then
    echo
    echo "Latest V1 trial score:"
    python3 tools/analyze-watch-sensor-trials.py "$trials" || true
  fi
}

run_all() {
  local profile="${1:-${RAISE_GATEWAY_PROFILE:-$DEFAULT_PROFILE}}"
  local session
  prepare_session "$profile"
  session="$(resolve_session)"

  echo
  read -r -p "Complete one short Native Raise AI question on the Watch, then press Enter to verify E2E. " _
  verify_e2e "$session"

  echo
  read -r -p "Collect 30 mouth raises + 100 non-trigger trials, then press Enter to verify V1. " _
  verify_v1 "$session"
}

case "${1:-}" in
  prepare)
    prepare_session "${2:-}"
    ;;
  verify-e2e)
    verify_e2e "${2:-}"
    ;;
  verify-v1)
    verify_v1 "${2:-}"
    ;;
  status)
    show_status "${2:-}"
    ;;
  all)
    run_all "${2:-}"
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "Unknown command: $1"
    usage
    exit 2
    ;;
esac
 || {
    echo "Could not compute APK SHA-256."
    exit 1
  }

  bash ./provision-watch-gateway.command "$profile"

  adb="$(find_adb || true)"
  [ -n "$adb" ] || { echo "ADB not found after install"; exit 1; }
  target="${ANDROID_SERIAL:-$(find_watch "$adb" | head -n 1)}"
  [ -n "$target" ] || { echo "Watch disconnected after install"; exit 1; }

  model="$("$adb" -s "$target" shell getprop ro.product.model | tr -d '\r')"
  installed_version="$("$adb" -s "$target" shell dumpsys package "$PACKAGE" |
    sed -n 's/^[[:space:]]*versionName=//p' | head -n 1 | tr -d '\r')"
  [ "$installed_version" = "$version" ] || {
    echo "Installed Watch version $installed_version does not match prepared version $version"
    exit 1
  }

  echo "Clearing prior validation evidence only..."
  "$adb" -s "$target" shell run-as "$PACKAGE" sh -c     "'rm -f files/watch-e2e-evidence.json files/sensor-traces.csv files/sensor-trials.csv'"
  "$adb" -s "$target" logcat -c || true
  "$adb" -s "$target" shell am start -n "$PACKAGE/.MainActivity" >/dev/null

  STARTED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"   SESSION_PATH="$session"   APP_VERSION="$version"   SOURCE_REVISION="$revision"   WATCH_MODEL="$model"   INSTALL_MODE="$install_mode"   APK_SHA256="$apk_sha"   python3 - <<'PY'
import json
import os
from pathlib import Path
session = Path(os.environ["SESSION_PATH"])
payload = {
    "schema_version": 1,
    "started_at_utc": os.environ["STARTED_AT_UTC"],
    "app_version": os.environ["APP_VERSION"],
    "source_revision": os.environ["SOURCE_REVISION"],
    "watch_model": os.environ["WATCH_MODEL"],
    "install_mode": os.environ["INSTALL_MODE"],
    "apk_sha256": os.environ["APK_SHA256"],
    "e2e_passed": False,
    "v1_gate_passed": False,
}
(session / "session.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

  printf '%s\n' "$session" > "$LATEST_SESSION_FILE"
  echo
  echo "PREPARE PASS"
  echo "On the Watch: open Native Raise AI and complete one short normal AI question."
  echo "Immediately afterwards run:"
  echo "  bash ./physical-validation.command verify-e2e '$session'"
  printf '%s\n' "$session"
}

verify_e2e() {
  local session
  session="$(resolve_session "${1:-}")"
  [ -f "$session/session.json" ] || { echo "Invalid session: $session"; exit 1; }
  require_command python3

  local version revision
  version="$(json_get "$session/session.json" app_version)"
  revision="$(json_get "$session/session.json" source_revision)"

  RAISE_OUTPUT_DIR="$session"   RAISE_E2E_EXPECT_APP_VERSION="$version"   RAISE_E2E_EXPECT_SOURCE_REVISION="$revision"     bash ./pull-diagnostics.command

  local diag evidence result
  diag="$(find "$session" -maxdepth 1 -type d -name 'watch-diagnostics-*' -print | sort | tail -n 1)"
  [ -n "$diag" ] || { echo "No diagnostics directory produced"; exit 1; }
  evidence="$diag/watch-e2e-evidence.json"
  [ -s "$evidence" ] || {
    echo "No fresh Watch E2E evidence found."
    echo "Complete a native Watch AI request and retry immediately."
    exit 1
  }

  result="$session/e2e-result.json"
  python3 tools/validate-watch-e2e-evidence.py     "$evidence"     --expect-route quick_ai     --max-latency-ms 15000     --max-age-seconds 300     --require-answer     --expect-app-version "$version"     --expect-source-revision "$revision" | tee "$result"

  json_set "$session/session.json" e2e_passed true
  json_set "$session/session.json" e2e_verified_at_utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "E2E PASS — exact Watch build ${version} @ ${revision}"
  echo "Next: collect at least 30 mouth raises and 100 representative non-trigger trials."
  echo "Then run:"
  echo "  bash ./physical-validation.command verify-v1 '$session'"
}

verify_v1() {
  local session
  session="$(resolve_session "${1:-}")"
  [ -f "$session/session.json" ] || { echo "Invalid session: $session"; exit 1; }
  require_command python3

  local e2e_passed version revision
  e2e_passed="$(json_get "$session/session.json" e2e_passed)"
  [ "$e2e_passed" = "true" ] || {
    echo "Refusing V1 gate before this session's fresh E2E gate has passed."
    echo "Run verify-e2e first."
    exit 1
  }
  version="$(json_get "$session/session.json" app_version)"
  revision="$(json_get "$session/session.json" source_revision)"

  RAISE_OUTPUT_DIR="$session"   RAISE_REQUIRE_V1_TRACE_GATE=1   RAISE_REQUIRE_V1_TRIAL_GATE=1     bash ./pull-watch-data.command

  local trials result
  trials="$(find "$session" -maxdepth 1 -type f -name 'watch-sensor-trials-*.csv' -print | sort | tail -n 1)"
  [ -n "$trials" ] || { echo "No trial evidence was exported"; exit 1; }

  result="$session/v1-result.json"
  python3 tools/analyze-watch-sensor-trials.py "$trials" \
    --expect-app-version "$version" \
    --expect-source-revision "$revision" \
    --require-v1-gate | tee "$result"

  json_set "$session/session.json" v1_gate_passed true
  json_set "$session/session.json" v1_verified_at_utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "V1 RELIABILITY PASS"
  echo "Evidence directory: $session"
}

show_status() {
  local session
  session="$(resolve_session "${1:-}")"
  [ -f "$session/session.json" ] || { echo "Invalid session: $session"; exit 1; }
  cat "$session/session.json"

  local trials
  trials="$(find "$session" -maxdepth 1 -type f -name 'watch-sensor-trials-*.csv' -print | sort | tail -n 1)"
  if [ -n "$trials" ] && command -v python3 >/dev/null 2>&1; then
    echo
    echo "Latest V1 trial score:"
    python3 tools/analyze-watch-sensor-trials.py "$trials" || true
  fi
}

run_all() {
  local profile="${1:-${RAISE_GATEWAY_PROFILE:-$DEFAULT_PROFILE}}"
  local session
  prepare_session "$profile"
  session="$(resolve_session)"

  echo
  read -r -p "Complete one short Native Raise AI question on the Watch, then press Enter to verify E2E. " _
  verify_e2e "$session"

  echo
  read -r -p "Collect 30 mouth raises + 100 non-trigger trials, then press Enter to verify V1. " _
  verify_v1 "$session"
}

case "${1:-}" in
  prepare)
    prepare_session "${2:-}"
    ;;
  verify-e2e)
    verify_e2e "${2:-}"
    ;;
  verify-v1)
    verify_v1 "${2:-}"
    ;;
  status)
    show_status "${2:-}"
    ;;
  all)
    run_all "${2:-}"
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "Unknown command: $1"
    usage
    exit 2
    ;;
esac
 || {
    echo "Could not compute APK SHA-256."
    exit 1
  }

  bash ./provision-watch-gateway.command "$profile"

  adb="$(find_adb || true)"
  [ -n "$adb" ] || { echo "ADB not found after install"; exit 1; }
  target="${ANDROID_SERIAL:-$(find_watch "$adb" | head -n 1)}"
  [ -n "$target" ] || { echo "Watch disconnected after install"; exit 1; }

  model="$("$adb" -s "$target" shell getprop ro.product.model | tr -d '\r')"
  installed_version="$("$adb" -s "$target" shell dumpsys package "$PACKAGE" |
    sed -n 's/^[[:space:]]*versionName=//p' | head -n 1 | tr -d '\r')"
  [ "$installed_version" = "$version" ] || {
    echo "Installed Watch version $installed_version does not match prepared version $version"
    exit 1
  }

  echo "Clearing prior validation evidence only..."
  "$adb" -s "$target" shell run-as "$PACKAGE" sh -c     "'rm -f files/watch-e2e-evidence.json files/sensor-traces.csv files/sensor-trials.csv'"
  "$adb" -s "$target" logcat -c || true
  "$adb" -s "$target" shell am start -n "$PACKAGE/.MainActivity" >/dev/null

  STARTED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"   SESSION_PATH="$session"   APP_VERSION="$version"   SOURCE_REVISION="$revision"   WATCH_MODEL="$model"   python3 - <<'PY'
import json
import os
from pathlib import Path
session = Path(os.environ["SESSION_PATH"])
payload = {
    "schema_version": 1,
    "started_at_utc": os.environ["STARTED_AT_UTC"],
    "app_version": os.environ["APP_VERSION"],
    "source_revision": os.environ["SOURCE_REVISION"],
    "watch_model": os.environ["WATCH_MODEL"],
    "e2e_passed": False,
    "v1_gate_passed": False,
}
(session / "session.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

  printf '%s\n' "$session" > "$LATEST_SESSION_FILE"
  echo
  echo "PREPARE PASS"
  echo "On the Watch: open Native Raise AI and complete one short normal AI question."
  echo "Immediately afterwards run:"
  echo "  bash ./physical-validation.command verify-e2e '$session'"
  printf '%s\n' "$session"
}

verify_e2e() {
  local session
  session="$(resolve_session "${1:-}")"
  [ -f "$session/session.json" ] || { echo "Invalid session: $session"; exit 1; }
  require_command python3

  local version revision
  version="$(json_get "$session/session.json" app_version)"
  revision="$(json_get "$session/session.json" source_revision)"

  RAISE_OUTPUT_DIR="$session"   RAISE_E2E_EXPECT_APP_VERSION="$version"   RAISE_E2E_EXPECT_SOURCE_REVISION="$revision"     bash ./pull-diagnostics.command

  local diag evidence result
  diag="$(find "$session" -maxdepth 1 -type d -name 'watch-diagnostics-*' -print | sort | tail -n 1)"
  [ -n "$diag" ] || { echo "No diagnostics directory produced"; exit 1; }
  evidence="$diag/watch-e2e-evidence.json"
  [ -s "$evidence" ] || {
    echo "No fresh Watch E2E evidence found."
    echo "Complete a native Watch AI request and retry immediately."
    exit 1
  }

  result="$session/e2e-result.json"
  python3 tools/validate-watch-e2e-evidence.py     "$evidence"     --expect-route quick_ai     --max-latency-ms 15000     --max-age-seconds 300     --require-answer     --expect-app-version "$version"     --expect-source-revision "$revision" | tee "$result"

  json_set "$session/session.json" e2e_passed true
  json_set "$session/session.json" e2e_verified_at_utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "E2E PASS — exact Watch build ${version} @ ${revision}"
  echo "Next: collect at least 30 mouth raises and 100 representative non-trigger trials."
  echo "Then run:"
  echo "  bash ./physical-validation.command verify-v1 '$session'"
}

verify_v1() {
  local session
  session="$(resolve_session "${1:-}")"
  [ -f "$session/session.json" ] || { echo "Invalid session: $session"; exit 1; }
  require_command python3

  local e2e_passed version revision
  e2e_passed="$(json_get "$session/session.json" e2e_passed)"
  [ "$e2e_passed" = "true" ] || {
    echo "Refusing V1 gate before this session's fresh E2E gate has passed."
    echo "Run verify-e2e first."
    exit 1
  }
  version="$(json_get "$session/session.json" app_version)"
  revision="$(json_get "$session/session.json" source_revision)"

  RAISE_OUTPUT_DIR="$session"   RAISE_REQUIRE_V1_TRACE_GATE=1   RAISE_REQUIRE_V1_TRIAL_GATE=1     bash ./pull-watch-data.command

  local trials result
  trials="$(find "$session" -maxdepth 1 -type f -name 'watch-sensor-trials-*.csv' -print | sort | tail -n 1)"
  [ -n "$trials" ] || { echo "No trial evidence was exported"; exit 1; }

  result="$session/v1-result.json"
  python3 tools/analyze-watch-sensor-trials.py "$trials" \
    --expect-app-version "$version" \
    --expect-source-revision "$revision" \
    --require-v1-gate | tee "$result"

  json_set "$session/session.json" v1_gate_passed true
  json_set "$session/session.json" v1_verified_at_utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "V1 RELIABILITY PASS"
  echo "Evidence directory: $session"
}

show_status() {
  local session
  session="$(resolve_session "${1:-}")"
  [ -f "$session/session.json" ] || { echo "Invalid session: $session"; exit 1; }
  cat "$session/session.json"

  local trials
  trials="$(find "$session" -maxdepth 1 -type f -name 'watch-sensor-trials-*.csv' -print | sort | tail -n 1)"
  if [ -n "$trials" ] && command -v python3 >/dev/null 2>&1; then
    echo
    echo "Latest V1 trial score:"
    python3 tools/analyze-watch-sensor-trials.py "$trials" || true
  fi
}

run_all() {
  local profile="${1:-${RAISE_GATEWAY_PROFILE:-$DEFAULT_PROFILE}}"
  local session
  prepare_session "$profile"
  session="$(resolve_session)"

  echo
  read -r -p "Complete one short Native Raise AI question on the Watch, then press Enter to verify E2E. " _
  verify_e2e "$session"

  echo
  read -r -p "Collect 30 mouth raises + 100 non-trigger trials, then press Enter to verify V1. " _
  verify_v1 "$session"
}

case "${1:-}" in
  prepare)
    prepare_session "${2:-}"
    ;;
  verify-e2e)
    verify_e2e "${2:-}"
    ;;
  verify-v1)
    verify_v1 "${2:-}"
    ;;
  status)
    show_status "${2:-}"
    ;;
  all)
    run_all "${2:-}"
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "Unknown command: $1"
    usage
    exit 2
    ;;
esac
