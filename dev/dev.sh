#!/usr/bin/env bash
# Start or stop the catalog's dev installation with podman kube play directly.
# Credentials are prepared beforehand; for the shipped demo run dev/demo-credentials.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
    up)
        # prepare checks database volumes before it writes config or creates secrets.
        ./deploy prepare
        podman network exists myproduct || podman network create myproduct
        podman kube play --replace --network myproduct build/install.yaml
        ;;
    down)
        # Stops what the last prepare rendered; run it before removing a component.
        podman kube down build/install.yaml
        ;;
    *) echo 'Usage: dev/dev.sh up|down' >&2; exit 2 ;;
esac
