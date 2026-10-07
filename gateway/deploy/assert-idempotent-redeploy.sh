#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="${RAISE_CONFIG_DIR:-$HOME/.config/raiseai}"
ENV_FILE="$CONFIG_DIR/gateway.env"
CERT_FILE="$CONFIG_DIR/tls/gateway-cert.pem"
EXPECTED_REVISION="${RAISE_DEPLOY_REVISION:-}"

resolve_dependency() {
  local name="$1" resolved
  resolved="$(command -v "$name" || true)"
  if [ -z "$resolved" ] || [[ "$resolved" != /* ]] || [ ! -x "$resolved" ]; then
    echo "Raise idempotency verification requires an absolute executable $name binary" >&2
    return 1
  fi
  printf '%s\n' "$resolved"
}

OPENSSL_BIN="$(resolve_dependency openssl)" || exit 1
AWK_BIN="$(resolve_dependency awk)" || exit 1

read_env_value() {
  local key="$1" value
  if ! value="$("$AWK_BIN" -F= -v key="$key" '
    $1 == key {
      count += 1
      sub(/^[^=]*=/, "")
      value = $0
    }
    END {
      if (count != 1) {
        exit 2
      }
      print value
    }
  ' "$ENV_FILE")"; then
    echo "Expected exactly one $key in gateway env" >&2
    return 1
  fi
  printf '%s\n' "$value"
}

spki_sha256() {
  "$OPENSSL_BIN" x509 -in "$1" -pubkey -noout |
    "$OPENSSL_BIN" pkey -pubin -outform DER 2>/dev/null |
    "$OPENSSL_BIN" dgst -sha256 |
    "$AWK_BIN" '{print $2}'
}

if [ ! -s "$ENV_FILE" ] || [ ! -s "$CERT_FILE" ]; then
  echo "Raise gateway must be installed before idempotency verification" >&2
  exit 1
fi

before_token="$(read_env_value RAISE_GATEWAY_TOKEN)"
before_spki="$(spki_sha256 "$CERT_FILE")"
before_revision="$(read_env_value RAISE_DEPLOY_REVISION)"

if [ "${#before_token}" -lt 32 ] || [ "${#before_spki}" -ne 64 ]; then
  echo "Invalid pre-redeploy credential state" >&2
  exit 1
fi

if [[ ! "$before_revision" =~ ^[A-Za-z0-9._-]{1,128}$ ]]; then
  echo "Invalid pre-redeploy revision state" >&2
  exit 1
fi

if [ -n "$EXPECTED_REVISION" ] && [ "$before_revision" != "$EXPECTED_REVISION" ]; then
  echo "Idempotency failure: pre-redeploy revision does not match expected revision" >&2
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

if [ "$before_revision" != "$after_revision" ]; then
  echo "Idempotency failure: deploy revision changed" >&2
  exit 1
fi

if [ -n "$EXPECTED_REVISION" ] && [ "$after_revision" != "$EXPECTED_REVISION" ]; then
  echo "Idempotency failure: post-redeploy revision does not match expected revision" >&2
  exit 1
fi

echo "Idempotent redeploy verified: token, TLS public key and deploy revision preserved"
