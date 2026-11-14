#!/usr/bin/env bash
# Run a local SQL file in one component's running dev database (backlog 81):
#   dev/seed-db.sh <component> <sql file>
# Run it after ./dev/dev.sh up, once the component's migrations have completed.
set -euo pipefail
exec python3 -B "$(dirname "$0")/seed_db.py" "$@"
