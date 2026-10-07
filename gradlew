#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
GRADLE_VERSION="9.6.0"
GRADLE_BIN_SHA256="bbaeb2fef8710818cf0e261201dab964c572f92b942812df0c3620d62a529a01"
TOOLS="$ROOT/.tools"
DIST="$TOOLS/gradle-$GRADLE_VERSION"
ZIP="$TOOLS/gradle-$GRADLE_VERSION-bin.zip"

sha256_file() {
  sha256sum "$1" | awk '{print tolower($1)}'
}

archive_is_verified() {
  [ -f "$ZIP" ] || return 1
  [ ! -L "$ZIP" ] || return 1
  [ "$(sha256_file "$ZIP")" = "$GRADLE_BIN_SHA256" ]
}

distribution_matches_archive() {
  [ -d "$DIST" ] || return 1
  [ ! -L "$DIST" ] || return 1
  [ -x "$DIST/bin/gradle" ] || return 1

  local entry relative path
  local expected_count=0
  local actual_count

  while IFS= read -r entry; do
    case "$entry" in
      "gradle-$GRADLE_VERSION/"*) ;;
      *) return 1 ;;
    esac
    case "$entry" in
      */) continue ;;
    esac

    relative="${entry#gradle-$GRADLE_VERSION/}"
    path="$DIST/$relative"
    [ -f "$path" ] || return 1
    [ ! -L "$path" ] || return 1
    cmp -s <(unzip -p "$ZIP" "$entry") "$path" || return 1
    expected_count=$((expected_count + 1))
  done < <(unzip -Z1 "$ZIP")

  actual_count="$(find "$DIST" -type f -print | wc -l | tr -d '[:space:]')"
  [ "$actual_count" = "$expected_count" ] || return 1

  if find "$DIST" ! -type d ! -type f -print -quit | grep -q .; then
    return 1
  fi
}

if [ -L "$TOOLS" ]; then
  echo "Refusing symlinked Gradle tools directory: $TOOLS" >&2
  exit 1
fi
mkdir -p "$TOOLS"

if archive_is_verified && distribution_matches_archive; then
  echo "Using verified cached Gradle $GRADLE_VERSION."
  exec "$DIST/bin/gradle" "$@"
fi

if archive_is_verified; then
  echo "Cached Gradle installation failed integrity check; restoring from verified archive…" >&2
else
  if [ -e "$ZIP" ] || [ -L "$ZIP" ]; then
    rm -f "$ZIP"
  fi

  echo "Gradle $GRADLE_VERSION is not cached; downloading once…"
  rm -f "$ZIP.part"
  curl -L --fail --retry 3 "https://services.gradle.org/distributions/gradle-$GRADLE_VERSION-bin.zip" -o "$ZIP.part"

  actual_sha256="$(sha256_file "$ZIP.part")"
  if [ "$actual_sha256" != "$GRADLE_BIN_SHA256" ]; then
    rm -f "$ZIP.part"
    echo "Gradle distribution checksum mismatch." >&2
    echo "Expected: $GRADLE_BIN_SHA256" >&2
    echo "Actual:   $actual_sha256" >&2
    exit 1
  fi

  mv "$ZIP.part" "$ZIP"
fi

rm -rf "$DIST"
unzip -q "$ZIP" -d "$TOOLS"

if ! distribution_matches_archive; then
  rm -rf "$DIST"
  echo "Gradle distribution install integrity check failed." >&2
  exit 1
fi

exec "$DIST/bin/gradle" "$@"
