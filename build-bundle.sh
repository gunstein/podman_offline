#!/usr/bin/env bash
# Build the defined offline bundles from their component manifests.
set -euo pipefail

cd "$(dirname "$0")"
exec python3 -B bundle.py "$@"
