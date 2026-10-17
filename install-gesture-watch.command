#!/usr/bin/env bash
set -euo pipefail

# Installs this feature branch, never a silently older main build.
# Usage: bash ./install-gesture-watch.command [watch-ip:port]
# Optional: RAISE_INSTALL_FROM=local | ci | auto (default)
REPO="Zennay/RaiseAI"
FEATURE_BRANCH="feature/gesture-permissions-setup-20261010"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*"; }

case "${1:-}" in
  -h|--help)
    cat <<'HELP'
Raise AI gesture/permissions Watch 7 installer (macOS).
Usage: bash ./install-gesture-watch.command [watch-ip:port]

Default: download an exact successful PR build from GitHub Actions if available,
otherwise build this checkout locally with Android Studio and install via ADB.
RAISE_INSTALL_FROM=ci   requires a successful PR artifact; no local fallback.
RAISE_INSTALL_FROM=local builds on Mac, without GitHub CLI.
ANDROID_SERIAL=<adb-serial> binds the install to a specific watch.
HELP
    exit 0
    ;;
esac
[ "${#}" -le 1 ] || die "Expected at most one optional watch-ip:port"
[ "$(uname -s)" = "Darwin" ] || die "This installer is intended for macOS."
command -v git >/dev/null 2>&1 || die "Git is required (install Xcode Command Line Tools)."
[ -f VERSION.txt ] && [ -f upgrade-watch.command ] && [ -f install-watch-apk.command ] ||
  die "Run this script from a full RaiseAI feature-branch checkout."

CURRENT_BRANCH="$(git branch --show-current)"
[ "$CURRENT_BRANCH" = "$FEATURE_BRANCH" ] ||
  die "Wrong branch ($CURRENT_BRANCH). Checkout $FEATURE_BRANCH, not main."
[ -z "$(git status --porcelain --untracked-files=normal)" ] ||
  die "Uncommitted files found. Commit/stash them before installing a pinned source."
REVISION="$(git rev-parse HEAD)"
printf '%s' "$REVISION" | grep -Eq '^[0-9a-f]{40}$' ||
  die "Cannot establish the exact feature source revision."

# Prevent a stale clone silently installing an older version of this feature.
if git fetch --quiet origin "$FEATURE_BRANCH"; then
  REMOTE_REVISION="$(git rev-parse FETCH_HEAD)"
  [ "$REVISION" = "$REMOTE_REVISION" ] ||
    die "Feature branch was updated. Run: git pull --ff-only origin $FEATURE_BRANCH"
else
  die "Unable to verify latest feature branch. Check internet access and retry."
fi

VERSION="$(tr -d '\r\n' < VERSION.txt)"
[ "$VERSION" = "1.5.4" ] ||
  die "Unexpected version $VERSION. This installer requires gesture release v1.5.4."
info "Raise AI gesture v$VERSION, source $REVISION"

INSTALL_FROM="${RAISE_INSTALL_FROM:-auto}"
case "$INSTALL_FROM" in auto|ci|local) ;; *) die "RAISE_INSTALL_FROM must be auto, ci or local";; esac

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/raiseai-gesture-install.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT
export RAISE_INSTALLED_WATCH_SERIAL_FILE="$WORK_DIR/installed-watch-serial"
export RAISE_INSTALLED_APK_SHA256_FILE="$WORK_DIR/installed-apk-sha256"
if [ -n "${1:-}" ]; then
  export WATCH_ENDPOINT="$1"
fi

APK=""
if [ "$INSTALL_FROM" != "local" ]; then
  if command -v gh >/dev/null 2>&1 && gh auth status --hostname github.com >/dev/null 2>&1; then
    info "Checking for a successful exact-source GitHub Watch APK…"
    RUNS="$(gh run list --repo "$REPO" --workflow watch-app-test.yml \
      --branch "$FEATURE_BRANCH" --event pull_request --status success \
      --limit 50 --json databaseId,headSha \
      --jq ".[] | select(.headSha == \"$REVISION\") | .databaseId" 2>/dev/null || true)"
    RUN_ID="$(printf '%s\n' "$RUNS" | grep -E '^[0-9]+$' | head -n 1 || true)"
    if [ -n "$RUN_ID" ]; then
      mkdir -p "$WORK_DIR/ci"
      ARTIFACT="RaiseAI-Watch7-v${VERSION}-${RUN_ID}"
      info "Downloading exact PR build #$RUN_ID ($ARTIFACT)…"
      if gh run download "$RUN_ID" --repo "$REPO" \
           --name "$ARTIFACT" --dir "$WORK_DIR/ci"; then
        [ -f "$WORK_DIR/ci/app-debug.apk" ] ||
          die "Successful workflow did not contain expected app-debug.apk; refusing fallback."
        APK="$WORK_DIR/ci/app-debug.apk"
      elif [ "$INSTALL_FROM" = "ci" ]; then
        die "Downloading the exact PR APK failed."
      else
        info "No usable CI artifact downloaded; falling back to local Mac build."
      fi
    fi
  else
    info "GitHub CLI unavailable or not authenticated; cannot download a CI APK."
  fi
  if [ -z "$APK" ] && [ "$INSTALL_FROM" = "ci" ]; then
    die "No successful CI artifact for this exact commit. Run 'gh auth login' or use RAISE_INSTALL_FROM=local."
  fi
fi

if [ -n "$APK" ]; then
  info "Installing CI-tested gesture APK via the existing Watch installer…"
  bash ./install-watch-apk.command "$APK" "${WATCH_ENDPOINT:-}"
else
  info "Building exact feature source on this Mac (requires Android Studio + SDK 35)…"
  info "For a missing SDK, see https://developer.android.com/studio"
  bash ./upgrade-watch.command
fi

[ -s "$RAISE_INSTALLED_WATCH_SERIAL_FILE" ] ||
  die "Installer did not report a bound Watch; installation cannot be verified."
WATCH_SERIAL="$(tr -d '\r\n' < "$RAISE_INSTALLED_WATCH_SERIAL_FILE")"
SDK_DIR="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}"
ADB="$SDK_DIR/platform-tools/adb"
[ -x "$ADB" ] || die "Cannot find ADB to verify installed app: $ADB"
PACKAGE_DUMP="$("$ADB" -s "$WATCH_SERIAL" shell dumpsys package nl.zennay.raiseai)" ||
  die "Cannot read installed package from Watch $WATCH_SERIAL"
printf '%s\n' "$PACKAGE_DUMP" | grep -Eq "versionName=${VERSION}([[:space:]]|$)" ||
  die "Watch does not report installed version $VERSION."
printf '%s\n' "$PACKAGE_DUMP" | grep -Eq 'versionCode=21([[:space:]]|$)' ||
  die "Watch does not report gesture release versionCode=21."

info ""
info "SUCCESS: Raise AI gesture v$VERSION installed on Watch $WATCH_SERIAL."
info "Selected AI defaults to Gemini; existing Native preference is preserved."
info "Open Raise AI → Hands-free setup → confirm background grant →"
info "Calibrate mouth pose → Enable raise-to-talk → Test raise gesture."
info "Hardware wake-up and Gemini listening still require a physical wrist test."
