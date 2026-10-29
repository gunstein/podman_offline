#!/usr/bin/env bash
# Start or stop the catalog's dev installation with podman kube play directly.
# Credentials are prepared beforehand; for the shipped demo run dev/demo-credentials.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
    up)
        # prepare checks database volumes before it writes config or creates secrets.
        ./deploy.sh prepare
        # The shared network carries the product name from bundles.yaml.
        product=$(python3 -B -c 'from deployment import catalog, common; print(catalog.product_name(common.ROOT))')
        podman network exists "$product" || podman network create "$product"
        # --no-hosts: a host /etc/hosts line for the public name (often 127.0.0.1)
        # must not reach the containers; they resolve it to the proxy (backlog 76).
        podman kube play --replace --no-hosts --network "$product" build/install.yaml
        ;;
    down)
        # Stops what the last prepare rendered; run it before removing a component.
        podman kube down build/install.yaml
        ;;
    *) echo 'Usage: dev/dev.sh up|down' >&2; exit 2 ;;
esac
