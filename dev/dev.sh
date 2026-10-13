#!/usr/bin/env bash
# Start or stop the dev installation with podman kube play directly.
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
    up)
        if [[ ! -f config.yaml ]]; then install -m 0600 config.example.yaml config.yaml; fi
        hostname=$(python3 - <<'DEV_HOST'
from urllib.parse import urlsplit
import deploy
print(urlsplit(deploy.load_config(deploy.CONFIG)["PUBLIC_ORIGIN"]).hostname)
DEV_HOST
)
        for component in core app1 app2 help; do
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
