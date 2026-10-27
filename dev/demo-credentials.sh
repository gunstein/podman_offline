#!/usr/bin/env bash
# Demo only: create the shipped demo's CA, certificates and user passwords in
# build/dev. Generic components bring their own credentials. Usage:
#   dev/demo-credentials.sh && dev/dev.sh up
set -euo pipefail
cd "$(dirname "$0")/.."
hostname=$(python3 -B - <<'DEMO_HOST'
from urllib.parse import urlsplit
from deployment import deploy

known, settings = deploy.dev_settings()
# Check manifests and database state before certificates, config output or secrets.
deploy.check_dev_components(known, settings)
print(urlsplit(settings["platform"]["PUBLIC_ORIGIN"]).hostname)
DEMO_HOST
)
for component in platform identity app1 app2 app3 help; do
    bash ./dev/generate-certificates.sh --root build/dev "$component" "$hostname"
done
# app3's backend trusts the proxy through this environment's CA (backlog 70);
# the demo PKI has one level, so the CA is both root and issuing CA.
install -d -m 0700 build/dev/app3/cert
install -m 0644 build/dev/PKI/private/ca.crt build/dev/app3/cert/root.crt
install -m 0644 build/dev/PKI/private/ca.crt build/dev/app3/cert/ca.crt
