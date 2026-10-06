#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GATEWAY_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PUBLIC_HOST="${RAISE_PUBLIC_HOST:-$(hostname -f)}"
PORT="${RAISE_PUBLIC_PORT:-8787}"
DEPLOY_REVISION="${RAISE_DEPLOY_REVISION:-unknown}"

if [[ ! "$DEPLOY_REVISION" =~ ^[A-Za-z0-9._-]{1,128}$ ]]; then
  echo "Invalid RAISE_DEPLOY_REVISION" >&2
  exit 1
fi

valid_public_host() {
  local host="$1" label
  [ -n "$host" ] && [ "${#host}" -le 253 ] || return 1
  [[ ! "$host" =~ [[:space:][:cntrl:]] ]] || return 1
  [[ "$host" != .* && "$host" != *. && "$host" != *..* ]] || return 1
  IFS='.' read -r -a labels <<< "$host"
  for label in "${labels[@]}"; do
    [ -n "$label" ] && [ "${#label}" -le 63 ] || return 1
    [[ "$label" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$ ]] || return 1
  done
}

is_ipv4_host() {
  local host="$1" octet
  local -a octets
  [[ "$host" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || return 1
  IFS='.' read -r -a octets <<< "$host"
  [ "${#octets[@]}" -eq 4 ] || return 1
  for octet in "${octets[@]}"; do
    (( 10#$octet <= 255 )) || return 1
  done
}

if ! valid_public_host "$PUBLIC_HOST"; then
  echo "Invalid RAISE_PUBLIC_HOST" >&2
  exit 1
fi

PUBLIC_HOST_SAN="DNS:$PUBLIC_HOST"
if is_ipv4_host "$PUBLIC_HOST"; then
  PUBLIC_HOST_SAN="IP:$PUBLIC_HOST"
fi

if [[ ! "$PORT" =~ ^[1-9][0-9]{0,4}$ ]] || (( 10#$PORT > 65535 )); then
  echo "Invalid RAISE_PUBLIC_PORT" >&2
  exit 1
fi

CONFIG_DIR="${RAISE_CONFIG_DIR:-$HOME/.config/raiseai}"
TLS_DIR="$CONFIG_DIR/tls"
ENV_FILE="$CONFIG_DIR/gateway.env"
WATCH_PROFILE="$CONFIG_DIR/watch-gateway.properties"
INSTALL_DIR="$HOME/.local/share/raise-gateway"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_FILE="$UNIT_DIR/raise-gateway.service"

mkdir -p "$CONFIG_DIR" "$TLS_DIR" "$INSTALL_DIR" "$UNIT_DIR"
chmod 700 "$CONFIG_DIR" "$TLS_DIR"

upsert_env() {
  local key="$1" value="$2" tmp
  tmp="$(mktemp)"
  if [ -f "$ENV_FILE" ]; then
    grep -v "^$key=" "$ENV_FILE" > "$tmp" || true
  fi
  printf '%s=%s\n' "$key" "$value" >> "$tmp"
  chmod 600 "$tmp"
  mv "$tmp" "$ENV_FILE"
}

TOKEN="$(awk -F= '/^RAISE_GATEWAY_TOKEN=/{sub(/^[^=]*=/,"");print;exit}' "$ENV_FILE" 2>/dev/null || true)"
if [ "${#TOKEN}" -lt 32 ]; then
  TOKEN="$(openssl rand -hex 32)"
fi

CERT="$TLS_DIR/gateway-cert.pem"
KEY="$TLS_DIR/gateway-key.pem"

if [ ! -s "$CERT" ] || [ ! -s "$KEY" ]; then
  openssl req -x509 -newkey ec     -pkeyopt ec_paramgen_curve:P-256     -sha256 -nodes -days 1825     -keyout "$KEY"     -out "$CERT"     -subj "/CN=$PUBLIC_HOST"     -addext "subjectAltName=$PUBLIC_HOST_SAN"
  chmod 600 "$KEY"
  chmod 644 "$CERT"
fi

SPKI_SHA256="$(
  openssl x509 -in "$CERT" -pubkey -noout |
    openssl pkey -pubin -outform DER 2>/dev/null |
    openssl dgst -sha256 |
    awk '{print $2}'
)"

if [ "${#SPKI_SHA256}" -ne 64 ]; then
  echo "Could not derive TLS public-key pin" >&2
  exit 1
fi

upsert_env RAISE_HOST "0.0.0.0"
upsert_env RAISE_PORT "$PORT"
upsert_env RAISE_GATEWAY_TOKEN "$TOKEN"
upsert_env RAISE_TLS_CERT "$CERT"
upsert_env RAISE_TLS_KEY "$KEY"
upsert_env RAISE_DEPLOY_REVISION "$DEPLOY_REVISION"

rm -rf "$INSTALL_DIR/src"
cp -a "$GATEWAY_ROOT/src" "$INSTALL_DIR/src"
cp "$GATEWAY_ROOT/package.json" "$INSTALL_DIR/package.json"

cat > "$UNIT_FILE" <<EOF
[Unit]
Description=Raise AI Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$ENV_FILE
ExecStart=/usr/bin/node $INSTALL_DIR/src/server.mjs
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict

[Install]
WantedBy=default.target
EOF

if [ -z "${XDG_RUNTIME_DIR:-}" ] && [ -d "/run/user/$(id -u)" ]; then
  export XDG_RUNTIME_DIR="/run/user/$(id -u)"
fi
if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] &&
   [ -S "${XDG_RUNTIME_DIR:-/nonexistent}/bus" ]; then
  export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
fi

systemctl --user daemon-reload
systemctl --user enable raise-gateway.service
# restart (not just start) so a redeploy never keeps serving the previously loaded code
systemctl --user restart raise-gateway.service

cat > "$WATCH_PROFILE" <<EOF
url=https://$PUBLIC_HOST:$PORT
token=$TOKEN
spki_sha256=$SPKI_SHA256
EOF
chmod 600 "$WATCH_PROFILE"

RAISE_EXPECTED_REVISION="$DEPLOY_REVISION" \
RAISE_READY_URL="https://$PUBLIC_HOST:$PORT" \
node "$SCRIPT_DIR/wait-for-live.mjs"

echo "Raise gateway installed."
echo "URL: https://$PUBLIC_HOST:$PORT"
echo "SPKI SHA-256: $SPKI_SHA256"
echo "Revision: $DEPLOY_REVISION"
echo "Watch profile: $WATCH_PROFILE"
echo "Provider API keys remain only in: $ENV_FILE"
