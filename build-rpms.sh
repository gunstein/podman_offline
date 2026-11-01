#!/usr/bin/env bash
# Wrap the built offline bundles as RPMs (backlog 69); needs rpmbuild.
set -euo pipefail

cd "$(dirname "$0")"
exec python3 -B rpms.py "$@"
