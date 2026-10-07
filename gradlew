#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
GRADLE_VERSION="9.6.0"
GRADLE_BIN_SHA256="bbaeb2fef8710818cf0e261201dab964c572f92b942812df0c3620d62a529a01"
TOOLS="$ROOT/.tools"
DIST="$TOOLS/gradle-$GRADLE_VERSION"
ZIP="$TOOLS/gradle-$GRADLE_VERSION-bin.zip"

# Reuse an existing Gradle from a previous Raise AI folder when possible.
for candidate in \
  "$DIST/bin/gradle" \
  "$ROOT/../RaiseAI-Watch7/.tools/gradle-$GRADLE_VERSION/bin/gradle" \
  "$ROOT/../RaiseAI-Watch7 1/.tools/gradle-$GRADLE_VERSION/bin/gradle"; do
  if [ -x "$candidate" ]; then
    exec "$candidate" "$@"
  fi
done

mkdir -p "$TOOLS"
echo "Gradle $GRADLE_VERSION is not cached; downloading once…"
rm -f "$ZIP.part"
curl -L --fail --retry 3 "https://services.gradle.org/distributions/gradle-$GRADLE_VERSION-bin.zip" -o "$ZIP.part"

actual_sha256="$(sha256sum "$ZIP.part" | awk '{print tolower($1)}')"
if [ "$actual_sha256" != "$GRADLE_BIN_SHA256" ]; then
  rm -f "$ZIP.part"
  echo "Gradle distribution checksum mismatch." >&2
  echo "Expected: $GRADLE_BIN_SHA256" >&2
  echo "Actual:   $actual_sha256" >&2
  exit 1
fi

mv "$ZIP.part" "$ZIP"
rm -rf "$DIST"
unzip -q "$ZIP" -d "$TOOLS"
exec "$DIST/bin/gradle" "$@"
