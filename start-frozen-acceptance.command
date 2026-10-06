#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

DEFAULT_PROFILE="$HOME/.config/raiseai/watch-gateway.properties"
FETCHER="$SCRIPT_DIR/tools/fetch-frozen-physical-handoff.py"
MODE="run"
PROFILE="$DEFAULT_PROFILE"

usage() {
  cat <<'EOF'
Usage:
  bash ./start-frozen-acceptance.command [gateway-profile]
  bash ./start-frozen-acceptance.command --preflight-only [gateway-profile]

Starts the canonical frozen Raise AI v1.5.2 physical acceptance flow.

--preflight-only:
  Validate the intended Galaxy Watch 7, fetch the preserved frozen handoff and
  run its verify-only provenance checks, then stop before APK install or session
  creation.

Exactly one active ADB device must be connected, and it must be the intended
Galaxy Watch 7 (SM-L315F / SM_L315F).
EOF
}

case "${1:-}" in
  -h|--help|help)
    usage
    exit 0
    ;;
  --preflight-only)
    MODE="preflight"
    PROFILE="${2:-$DEFAULT_PROFILE}"
    if [ "$#" -gt 2 ]; then
      usage
      exit 2
    fi
    ;;
  -*)
    echo "Unknown option: $1"
    usage
    exit 2
    ;;
  "")
    ;;
  *)
    PROFILE="$1"
    if [ "$#" -gt 1 ]; then
      usage
      exit 2
    fi
    ;;
esac

command -v python3 >/dev/null 2>&1 || {
  echo "Required command not found: python3"
  exit 1
}
[ -f "$FETCHER" ] || {
  echo "Frozen handoff fetcher not found: $FETCHER"
  exit 1
}
[ -e "$PROFILE" ] || {
  echo "Gateway profile not found: $PROFILE"
  exit 1
}

RUN_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/raiseai-frozen-acceptance.XXXXXX")"
cleanup() {
  rm -rf "$RUN_ROOT"
}
trap cleanup EXIT INT TERM

PROFILE_SNAPSHOT="$RUN_ROOT/watch-gateway.properties"
PROFILE="$(python3 - "$PROFILE" "$PROFILE_SNAPSHOT" <<'PY'
import os
import stat
import sys

source = os.path.abspath(os.path.expanduser(sys.argv[1]))
destination = sys.argv[2]

if not hasattr(os, "O_NOFOLLOW"):
    raise SystemExit("Gateway profile snapshot requires O_NOFOLLOW support")

try:
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
except OSError as exc:
    raise SystemExit(
        f"Gateway profile must be a regular non-symlink file: {source}: {exc}"
    ) from exc

try:
    source_stat = os.fstat(source_fd)
    if not stat.S_ISREG(source_stat.st_mode):
        raise SystemExit(
            f"Gateway profile must be a regular non-symlink file: {source}"
        )
    with os.fdopen(source_fd, "rb", closefd=False) as handle:
        payload = handle.read()
finally:
    os.close(source_fd)

destination_fd = os.open(
    destination,
    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
    0o600,
)
try:
    with os.fdopen(destination_fd, "wb", closefd=False) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
finally:
    os.close(destination_fd)

os.chmod(destination, 0o600)
print(destination)
PY
)"

find_adb() {
  if command -v adb >/dev/null 2>&1; then
    command -v adb
    return
  fi
  for candidate in \
    "${ANDROID_SDK_ROOT:-}/platform-tools/adb" \
    "${ANDROID_HOME:-}/platform-tools/adb" \
    "$HOME/Library/Android/sdk/platform-tools/adb" \
    "$HOME/Android/Sdk/platform-tools/adb"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return
    fi
  done
  return 1
}

ADB="$(find_adb || true)"
[ -n "$ADB" ] || {
  echo "ADB not found. Install Android SDK Platform-Tools and connect the Watch first."
  exit 1
}

"$ADB" start-server >/dev/null
DEVICES="$("$ADB" devices | awk 'NR>1 && $2=="device" {print $1}')"
COUNT="$(printf '%s\n' "$DEVICES" | awk 'NF {n++} END {print n+0}')"
if [ "$COUNT" -ne 1 ]; then
  echo "Frozen acceptance requires exactly one active ADB device; found $COUNT."
  if [ "$COUNT" -gt 0 ]; then
    printf '%s\n' "$DEVICES" | sed 's/^/  /'
  fi
  echo "Disconnect other ADB phones, emulators or watches and retry."
  exit 1
fi
TARGET="$(printf '%s\n' "$DEVICES" | awk 'NF {print; exit}')"

MODEL="$("$ADB" -s "$TARGET" shell getprop ro.product.model 2>/dev/null | tr -d '\r' || true)"
CHARACTERISTICS="$("$ADB" -s "$TARGET" shell getprop ro.build.characteristics 2>/dev/null | tr -d '\r' || true)"
FEATURES="$("$ADB" -s "$TARGET" shell pm list features 2>/dev/null | tr -d '\r' || true)"

case "$MODEL" in
  SM-L315F|SM_L315F) ;;
  *)
    echo "Refusing frozen acceptance on unexpected Watch model: ${MODEL:-<unknown>} ($TARGET)"
    echo "Expected the intended Galaxy Watch 7: SM-L315F / SM_L315F."
    exit 1
    ;;
esac

if ! printf '%s' "$CHARACTERISTICS" | grep -qi watch &&
   ! printf '%s\n' "$FEATURES" | grep -q 'android.hardware.type.watch'; then
  echo "Selected ADB target does not identify as Wear OS: $TARGET"
  exit 1
fi

HANDOFF_DIR="$RUN_ROOT/handoff"
VERIFY_SOURCE="$RUN_ROOT/verify-source"
RUN_SOURCE="$RUN_ROOT/run-source"
SDK_SHIM="$RUN_ROOT/sdk"
mkdir -p "$SDK_SHIM/platform-tools" "$SDK_SHIM/build-tools"
ln -s "$ADB" "$SDK_SHIM/platform-tools/adb"

echo "Fetching canonical frozen v1.5.2 handoff..."
python3 "$FETCHER" --output "$HANDOFF_DIR"

echo
echo "Verifying frozen handoff before install..."
RAISE_RESTORE_DIR="$VERIFY_SOURCE" \
  bash "$HANDOFF_DIR/start-physical-handoff.command" --verify-only
rm -rf "$VERIFY_SOURCE"

echo
echo "Frozen handoff verified."
echo "Bound Watch: $MODEL ($TARGET)"

if [ "$MODE" = "preflight" ]; then
  echo "FROZEN-ACCEPTANCE PREFLIGHT PASS"
  echo "No APK was installed and no physical acceptance session was started."
  exit 0
fi

echo "Starting provenance-bound physical acceptance..."
echo

ANDROID_SERIAL="$TARGET" \
ANDROID_SDK_ROOT="$SDK_SHIM" \
ANDROID_HOME="$SDK_SHIM" \
RAISE_RESTORE_DIR="$RUN_SOURCE" \
  bash "$HANDOFF_DIR/start-physical-handoff.command" "$PROFILE"
