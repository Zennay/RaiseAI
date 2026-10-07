#!/bin/bash
set -euo pipefail

QUIET="${1:-}"
STATE_DIR="$HOME/.raiseai"
BIN_DIR="$STATE_DIR/bin"
LOG_DIR="$STATE_DIR/logs"
ENDPOINT_FILE="$STATE_DIR/watch-endpoint"
PLIST="$HOME/Library/LaunchAgents/nl.zennay.raiseai.adb-autoconnect.plist"
HELPER="$BIN_DIR/raiseai-adb-autoconnect"

if [ "$(uname -s)" != "Darwin" ]; then
  [ "$QUIET" = "--quiet" ] || echo "macOS only."
  exit 0
fi

SDK_DIR="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}"
ADB="$SDK_DIR/platform-tools/adb"
[ -x "$ADB" ] || { echo "adb not found at: $ADB"; exit 1; }

mkdir -p "$BIN_DIR" "$LOG_DIR" "$HOME/Library/LaunchAgents"

{
  printf '%s\n' '#!/bin/bash' 'set -u'
  printf 'ADB=%q\n' "$ADB"
  printf 'STATE_DIR=%q\n' "$STATE_DIR"
  printf 'ENDPOINT_FILE=%q\n' "$ENDPOINT_FILE"
  cat <<'HELPER_EOF'

"$ADB" start-server >/dev/null 2>&1 || exit 0

is_expected_watch() {
  local serial="${1:-}" model="" characteristics=""
  [ -n "$serial" ] || return 1
  model="$("$ADB" -s "$serial" shell getprop ro.product.model 2>/dev/null | tr -d '\r' || true)"
  characteristics="$("$ADB" -s "$serial" shell getprop ro.build.characteristics 2>/dev/null | tr -d '\r' || true)"
  case "$model" in
    SM-L315F|SM_L315F)
      printf '%s' "$characteristics" | grep -qi 'watch'
      return $?
      ;;
  esac
  return 1
}

find_watch() {
  local serial=""
  "$ADB" devices -l 2>/dev/null | awk 'NR>1 && $2=="device" {print $1}' | while IFS= read -r serial; do
    [ -n "$serial" ] || continue
    if is_expected_watch "$serial"; then
      printf '%s\n' "$serial"
      return 0
    fi
  done
}

TARGET="$(find_watch)"
[ -n "${TARGET:-}" ] && exit 0

if [ -f "$ENDPOINT_FILE" ]; then
  CACHED="$(tr -d '\r\n' < "$ENDPOINT_FILE")"
  if [ -n "${CACHED:-}" ]; then
    "$ADB" connect "$CACHED" >/dev/null 2>&1 || true
    sleep 1
    if is_expected_watch "$CACHED"; then
      exit 0
    fi
  fi
fi

while IFS= read -r ENDPOINT; do
  [ -n "${ENDPOINT:-}" ] || continue
  "$ADB" connect "$ENDPOINT" >/dev/null 2>&1 || continue
  sleep 1
  if is_expected_watch "$ENDPOINT"; then
    mkdir -p "$STATE_DIR"
    printf '%s\n' "$ENDPOINT" > "$ENDPOINT_FILE"
    exit 0
  fi
done < <(
  "$ADB" mdns services 2>/dev/null |
    awk '/_adb-tls-connect[.]_tcp/ {print $3}'
)

exit 0
HELPER_EOF
} > "$HELPER"

chmod +x "$HELPER"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>nl.zennay.raiseai.adb-autoconnect</string>
  <key>ProgramArguments</key>
  <array>
    <string>$HELPER</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>30</integer>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/adb-autoconnect.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/adb-autoconnect.err.log</string>
</dict>
</plist>
EOF

DOMAIN="gui/$(id -u)"
launchctl bootout "$DOMAIN" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "$DOMAIN" "$PLIST"
launchctl kickstart -k "$DOMAIN/nl.zennay.raiseai.adb-autoconnect" >/dev/null 2>&1 || true

touch "$STATE_DIR/autoconnect-installed"

if [ -f "$HOME/.android/adbkey" ]; then
  mkdir -p "$STATE_DIR/adb-key-backup"
  cp -p "$HOME/.android/adbkey" "$STATE_DIR/adb-key-backup/adbkey"
  [ ! -f "$HOME/.android/adbkey.pub" ] ||
    cp -p "$HOME/.android/adbkey.pub" "$STATE_DIR/adb-key-backup/adbkey.pub"
  chmod 600 "$STATE_DIR/adb-key-backup/adbkey" 2>/dev/null || true
fi

if [ "$QUIET" != "--quiet" ]; then
  echo "Raise AI ADB auto-connect installed."
  echo "macOS will retry the paired Watch every 30 seconds."
  echo "Pairing is still required only if the Watch revokes/forgets this Mac."
fi
