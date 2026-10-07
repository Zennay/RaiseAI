#!/bin/bash
set -euo pipefail

ARTIFACT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROFILE=""
VERIFY_ONLY=0

usage() {
  echo "Usage: bash ./start-physical-handoff.command /path/to/watch-gateway.properties"
  echo "       bash ./start-physical-handoff.command --verify-only"
}

case "$#" in
  1)
    if [ "$1" = "--verify-only" ]; then
      VERIFY_ONLY=1
    else
      case "$1" in
        --*)
          usage
          exit 2
          ;;
      esac
      PROFILE="$1"
    fi
    ;;
  *)
    usage
    exit 2
    ;;
esac

IDENTITY="$ARTIFACT_DIR/BUILD-IDENTITY.txt"

shopt -s nullglob
apk_matches=("$ARTIFACT_DIR"/RaiseAI-v*-debug.apk)
bundle_matches=("$ARTIFACT_DIR"/RaiseAI-v*-source.bundle)
shopt -u nullglob

[ "${#apk_matches[@]}" -eq 1 ] || {
  echo "Physical handoff must contain exactly one RaiseAI-v*-debug.apk"
  exit 1
}
[ "${#bundle_matches[@]}" -eq 1 ] || {
  echo "Physical handoff must contain exactly one RaiseAI-v*-source.bundle"
  exit 1
}

APK="${apk_matches[0]}"
BUNDLE="${bundle_matches[0]}"
apk_name="${APK##*/}"
bundle_name="${BUNDLE##*/}"
handoff_version="${apk_name#RaiseAI-v}"
handoff_version="${handoff_version%-debug.apk}"
bundle_version="${bundle_name#RaiseAI-v}"
bundle_version="${bundle_version%-source.bundle}"

[ -n "$handoff_version" ] && [ "$handoff_version" = "$bundle_version" ] || {
  echo "Physical handoff APK/source bundle versions do not match."
  exit 1
}

if [ "$VERIFY_ONLY" -eq 0 ] && [ ! -f "$PROFILE" ]; then
  usage
  exit 2
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
  local count

  count="$(grep -c "^${key}=" "$IDENTITY" || true)"
  if [ "$count" -ne 1 ]; then
    echo "BUILD-IDENTITY.txt must contain exactly one ${key} entry." >&2
    return 1
  fi

  sed -n "s/^${key}=//p" "$IDENTITY" | tr -d '\r\n'
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

VERIFY_TMP_ROOT=""
if [ "$VERIFY_ONLY" -eq 1 ] && [ -z "${RAISE_RESTORE_DIR:-}" ]; then
  VERIFY_TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/raiseai-handoff-verify.XXXXXX")"
  RESTORE_DIR="$VERIFY_TMP_ROOT/source"
  trap 'rm -rf "$VERIFY_TMP_ROOT"' EXIT
else
  RESTORE_DIR="${RAISE_RESTORE_DIR:-$ARTIFACT_DIR/RaiseAI-v${handoff_version}-source}"
fi

[ ! -e "$RESTORE_DIR" ] || {
  echo "Restore directory already exists: $RESTORE_DIR"
  echo "Remove it or set RAISE_RESTORE_DIR to a fresh path."
  exit 1
}

git clone -q -b "$bundle_branch" "$BUNDLE" "$RESTORE_DIR"
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
