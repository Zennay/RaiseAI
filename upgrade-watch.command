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
  RAISE_BUILD_REVISION="${RAISE_BUILD_REVISION:-$(git rev-parse HEAD)}"
  export RAISE_BUILD_REVISION
fi

echo "Building Raise AI v$VERSION…"
echo "The build will fail automatically if the Watch ABI is wrong."
./gradlew :app:assembleDebug

exec ./install-watch-apk.command app/build/outputs/apk/debug/app-debug.apk