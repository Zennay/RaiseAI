#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
GRADLE_VERSION="9.6.0"
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

if command -v gradle >/dev/null 2>&1; then
  exec gradle "$@"
fi

mkdir -p "$TOOLS"
echo "Gradle $GRADLE_VERSION is not cached; downloading once…"
rm -f "$ZIP.part"
curl -L --fail --retry 3 "https://services.gradle.org/distributions/gradle-$GRADLE_VERSION-bin.zip" -o "$ZIP.part"
mv "$ZIP.part" "$ZIP"
rm -rf "$DIST"
unzip -q "$ZIP" -d "$TOOLS"
exec "$DIST/bin/gradle" "$@"
