#!/usr/bin/env bash
# Demo only: create the shipped demo's CA, certificates and user passwords in
# build/dev. Generic components bring their own credentials. Usage:
#   dev/demo-credentials.sh && dev/dev.sh up
set -euo pipefail
cd "$(dirname "$0")/.."
hostname=$(python3 -B - <<'DEMO_HOST'
from urllib.parse import urlsplit
from deployment import deploy

_, settings = deploy.dev_settings()
# Check current database state before certificates, config output or secret creation.
deploy.dev_database_preflight(settings)
print(urlsplit(settings["platform"]["PUBLIC_ORIGIN"]).hostname)
DEMO_HOST
)
for component in platform identity app1 app2 help; do
    bash ./scripts/generate-certificates.sh --root build/dev "$component" "$hostname"
done
