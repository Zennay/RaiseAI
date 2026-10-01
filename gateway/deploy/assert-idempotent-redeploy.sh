#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="${RAISE_CONFIG_DIR:-$HOME/.config/raiseai}"
ENV_FILE="$CONFIG_DIR/gateway.env"
CERT_FILE="$CONFIG_DIR/tls/gateway-cert.pem"
EXPECTED_REVISION="${RAISE_DEPLOY_REVISION:-}"

read_env_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE"
}

spki_sha256() {
  openssl x509 -in "$1" -pubkey -noout |
    openssl pkey -pubin -outform DER 2>/dev/null |
    openssl dgst -sha256 |
    awk '{print $2}'
}

if [ ! -s "$ENV_FILE" ] || [ ! -s "$CERT_FILE" ]; then
  echo "Raise gateway must be installed before idempotency verification" >&2
  exit 1
fi

before_token="$(read_env_value RAISE_GATEWAY_TOKEN)"
before_spki="$(spki_sha256 "$CERT_FILE")"

if [ "${#before_token}" -lt 32 ] || [ "${#before_spki}" -ne 64 ]; then
  echo "Invalid pre-redeploy credential state" >&2
  exit 1
fi

bash "$SCRIPT_DIR/install-user-gateway.sh" >/dev/null

after_token="$(read_env_value RAISE_GATEWAY_TOKEN)"
after_spki="$(spki_sha256 "$CERT_FILE")"
after_revision="$(read_env_value RAISE_DEPLOY_REVISION)"

if [ "$before_token" != "$after_token" ]; then
  echo "Idempotency failure: gateway token rotated" >&2
  exit 1
fi

if [ "$before_spki" != "$after_spki" ]; then
  echo "Idempotency failure: TLS public key rotated" >&2
  exit 1
fi

if [ -n "$EXPECTED_REVISION" ] && [ "$after_revision" != "$EXPECTED_REVISION" ]; then
  echo "Idempotency failure: deploy revision changed" >&2
  exit 1
fi

echo "Idempotent redeploy verified: token, TLS public key and deploy revision preserved"
