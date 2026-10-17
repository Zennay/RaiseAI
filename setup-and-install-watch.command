#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
cd "$SCRIPT_DIR"

if [ "$#" -ne 0 ]; then
  echo "Usage: ./setup-and-install-watch.command"
  exit 2
fi

echo "Raise AI first-time setup/install uses the same ABI-safe path as upgrades."
exec ./upgrade-watch.command
