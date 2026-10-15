#!/usr/bin/env bash
# Start or stop the dev installation with podman kube play directly.
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
    up)
        hostname=$(python3 - <<'DEV_HOST'
from urllib.parse import urlsplit
import deploy
# Explicit Podman dependency before certificates, config output or secret creation.
deploy.reject_legacy_layout(home=deploy.BUILD / "dev", volumes=True)
for component in ("platform", "app1", "app2"):
    deploy.database_preflight(
        deploy.component_defaults(component, dev=True),
        deploy.BUILD / "dev" / component / "config.yaml",
        deploy.ROOT / "components" / component / "manifests",
    )
print(urlsplit(deploy.component_defaults("platform", dev=True)["PUBLIC_ORIGIN"]).hostname)
DEV_HOST
)
        for component in platform app1 app2 help; do
            bash ./scripts/generate-certificates.sh --root build/dev "$component" "$hostname"
        done
        ./deploy prepare
        podman network exists myproduct || podman network create myproduct
        podman kube play --replace --network myproduct build/install.yaml
        ;;
    down)
        podman kube down build/install.yaml
        ;;
    *) echo 'Usage: dev/dev.sh up|down' >&2; exit 2 ;;
esac
