#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

SDK_DIR="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}"
ADB="$SDK_DIR/platform-tools/adb"
JAVA_HOME="${JAVA_HOME:-/Applications/Android Studio.app/Contents/jbr/Contents/Home}"
export JAVA_HOME
export PATH="$JAVA_HOME/bin:$SDK_DIR/platform-tools:$PATH"

[ -x "$JAVA_HOME/bin/java" ] || {
  echo "Android Studio Java not found at: $JAVA_HOME"
  exit 1
}
[ -x "$ADB" ] || { echo "adb not found at: $ADB"; exit 1; }
[ -f "$SDK_DIR/platforms/android-35/android.jar" ] || {
  echo "Android SDK Platform 35 not found under: $SDK_DIR"
  exit 1
}

printf 'sdk.dir=%s\n' "$SDK_DIR" > local.properties
VERSION="$(tr -d '\r\n' < VERSION.txt)"
GRADLE_VERSION="$(sed -n 's/.*versionName = "\([^"]*\)".*/\1/p' app/build.gradle.kts | head -n 1)"
[ "$VERSION" = "$GRADLE_VERSION" ] || {
  echo "Version mismatch: VERSION.txt=$VERSION, Gradle=$GRADLE_VERSION"
  exit 1
}

if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
    echo "Refusing evidence-capable build from a dirty Git worktree."
    echo "Commit/stash changes first so Watch evidence can attest the exact source revision."
    exit 1
  fi
  checked_out_revision="$(git rev-parse HEAD | tr 'A-F' 'a-f')"
  printf '%s' "$checked_out_revision" | grep -Eq '^[0-9a-f]{40}$' || {
    echo "Could not resolve an exact 40-character Git HEAD revision."
    exit 1
  }

  if [ "${RAISE_BUILD_REVISION+x}" = "x" ]; then
    requested_revision="$(printf '%s' "$RAISE_BUILD_REVISION" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | tr 'A-F' 'a-f')"
    printf '%s' "$requested_revision" | grep -Eq '^[0-9a-f]{40}$' || {
      echo "RAISE_BUILD_REVISION must be an exact 40-character Git revision."
      exit 1
    }
    [ "$requested_revision" = "$checked_out_revision" ] || {
      echo "RAISE_BUILD_REVISION does not match checked-out HEAD."
      echo "head=$checked_out_revision requested=$requested_revision"
      exit 1
    }
    RAISE_BUILD_REVISION="$requested_revision"
  else
    RAISE_BUILD_REVISION="$checked_out_revision"
  fi
  export RAISE_BUILD_REVISION
else
  echo "Git checkout required for evidence-capable Watch builds."
  exit 1
fi

echo "Building Raise AI v$VERSION…"
echo "Evidence build revision: $RAISE_BUILD_REVISION"
echo "The build will fail automatically if build identity or Watch ABI is wrong."
./gradlew :app:verifyEvidenceBuildIdentity :app:assembleDebug

exec ./install-watch-apk.command app/build/outputs/apk/debug/app-debug.apk
