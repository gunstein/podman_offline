#!/usr/bin/env bash
# Start eller stopp dev-installasjonen med direkte podman kube play.
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
    up)
        ./deploy prepare
        podman network exists myproduct || podman network create myproduct
        podman kube play --replace --network myproduct build/install.yaml
        ;;
    down)
        podman kube down build/install.yaml
        ;;
    *) echo 'Usage: dev/dev.sh up|down' >&2; exit 2 ;;
esac
