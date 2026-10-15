#!/usr/bin/env bash
# Build the three offline bundles from their component manifests.
set -euo pipefail

cd "$(dirname "$0")"
exec python3 bundle.py "$@"
