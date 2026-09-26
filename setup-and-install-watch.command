#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

echo "Race AI first-time setup/install uses the same ABI-safe path as upgrades."
exec ./upgrade-watch.command