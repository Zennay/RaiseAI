#!/bin/bash
set -euo pipefail

ARTIFACT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROFILE="${1:-}"
VERIFY_ONLY=0
if [ "${1:-}" = "--verify-only" ]; then
  VERIFY_ONLY=1
  PROFILE=""
fi

IDENTITY="$ARTIFACT_DIR/BUILD-IDENTITY.txt"
APK="$ARTIFACT_DIR/RaiseAI-v1.5.2-debug.apk"
BUNDLE="$ARTIFACT_DIR/RaiseAI-v1.5.2-source.bundle"

if [ "$VERIFY_ONLY" -eq 0 ]; then
  if [ -z "$PROFILE" ] || [ ! -f "$PROFILE" ]; then
    echo "Usage: bash ./start-physical-handoff.command /path/to/watch-gateway.properties"
    echo "       bash ./start-physical-handoff.command --verify-only"
    exit 2
  fi
fi

for command_name in git python3; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "Required command not found: $command_name"
    exit 1
  }
done

for required in "$IDENTITY" "$APK" "$BUNDLE"; do
  [ -f "$required" ] || {
    echo "Incomplete physical handoff: missing $required"
    exit 1
  }
done

read_identity() {
  local key="$1"
  sed -n "s/^${key}=//p" "$IDENTITY" | head -n 1 | tr -d '\r\n'
}

revision="$(read_identity source_revision | tr 'A-F' 'a-f')"
expected_apk_sha="$(read_identity apk_sha256 | tr 'A-F' 'a-f')"
expected_bundle_sha="$(read_identity source_bundle_sha256 | tr 'A-F' 'a-f')"

case "$revision" in
  *[!0-9a-f]*|'') echo "Invalid source_revision in BUILD-IDENTITY.txt"; exit 1 ;;
esac
[ "${#revision}" -eq 40 ] || { echo "source_revision must be 40 hex characters"; exit 1; }

case "$expected_apk_sha" in
  *[!0-9a-f]*|'') echo "Invalid apk_sha256 in BUILD-IDENTITY.txt"; exit 1 ;;
esac
[ "${#expected_apk_sha}" -eq 64 ] || { echo "apk_sha256 must be 64 hex characters"; exit 1; }

case "$expected_bundle_sha" in
  *[!0-9a-f]*|'') echo "Invalid source_bundle_sha256 in BUILD-IDENTITY.txt"; exit 1 ;;
esac
[ "${#expected_bundle_sha}" -eq 64 ] || { echo "source_bundle_sha256 must be 64 hex characters"; exit 1; }

actual_bundle_sha="$(python3 - "$BUNDLE" <<'PY'
import hashlib
import sys
from pathlib import Path
print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)"
[ "$actual_bundle_sha" = "$expected_bundle_sha" ] || {
  echo "Source bundle SHA-256 mismatch."
  exit 1
}

actual_apk_sha="$(python3 - "$APK" <<'PY'
import hashlib
import sys
from pathlib import Path
print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)"
[ "$actual_apk_sha" = "$expected_apk_sha" ] || {
  echo "APK SHA-256 mismatch."
  exit 1
}

bundle_ref="$(
  git bundle list-heads "$BUNDLE" |
    awk -v sha="$revision" 'tolower($1) == sha {print $2; exit}'
)"
[ -n "$bundle_ref" ] || {
  echo "Source bundle does not contain expected revision $revision"
  exit 1
}
bundle_branch="${bundle_ref#refs/heads/}"
[ -n "$bundle_branch" ] && [ "$bundle_branch" != "$bundle_ref" ] || {
  echo "Expected source revision is not exposed as a branch in the bundle."
  exit 1
}

RESTORE_DIR="${RAISE_RESTORE_DIR:-$ARTIFACT_DIR/RaiseAI-v1.5.2-source}"
if [ -e "$RESTORE_DIR" ]; then
  [ -d "$RESTORE_DIR/.git" ] || {
    echo "Restore path exists but is not a Git checkout: $RESTORE_DIR"
    exit 1
  }
  restored_revision="$(git -C "$RESTORE_DIR" rev-parse HEAD 2>/dev/null | tr 'A-F' 'a-f' || true)"
  [ "$restored_revision" = "$revision" ] || {
    echo "Existing restore revision does not match the handoff."
    echo "  expected: $revision"
    echo "  actual:   ${restored_revision:-<unresolved>}"
    echo "Remove the restore directory or set RAISE_RESTORE_DIR to a fresh path."
    exit 1
  }
  [ -z "$(git -C "$RESTORE_DIR" status --porcelain --untracked-files=normal)" ] || {
    echo "Existing restore checkout is dirty: $RESTORE_DIR"
    echo "Refusing to reuse it for physical evidence."
    exit 1
  }
  echo "Reusing exact clean restored source: $RESTORE_DIR"
else
  git clone -q -b "$bundle_branch" "$BUNDLE" "$RESTORE_DIR"
fi

test "$(git -C "$RESTORE_DIR" rev-parse HEAD | tr 'A-F' 'a-f')" = "$revision"
test -z "$(git -C "$RESTORE_DIR" status --porcelain --untracked-files=normal)"

python3 "$RESTORE_DIR/tools/verify-watch-apk-identity.py"   "$APK"   --expect-source-revision "$revision"   --expect-sha256 "$expected_apk_sha"

echo "Verified physical handoff:"
echo "  source revision: $revision"
echo "  APK SHA-256:     $expected_apk_sha"
echo "  source bundle:   $expected_bundle_sha"

if [ "$VERIFY_ONLY" -eq 1 ]; then
  echo "VERIFY-ONLY PASS"
  exit 0
fi

cd "$RESTORE_DIR"
RAISE_PREBUILT_APK="$APK" RAISE_EXPECT_APK_SHA256="$expected_apk_sha" exec bash ./physical-validation.command all "$PROFILE"
