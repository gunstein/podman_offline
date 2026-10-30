#!/usr/bin/env bash
# Start, restart or stop the catalog's dev installation with podman kube play directly.
# Credentials are prepared beforehand; for the shipped demo run dev/demo-credentials.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
# Generate localhost entries without inheriting a host loopback mapping. Podman
# regenerates /etc/hosts on every start, so each starting command selects it;
# scope it to that command and leave user Podman config intact.
hosts_policy="$PWD/quadlet/containers-hosts.conf"
case "${1:-}" in
    up)
        # prepare checks database volumes before it writes config or creates secrets.
        ./deploy.sh prepare
        # The shared network carries the product name from bundles.yaml.
        product=$(python3 -B -c 'from deployment import catalog, common; print(catalog.product_name(common.ROOT))')
        podman network exists "$product" || podman network create "$product"
        CONTAINERS_CONF_OVERRIDE="$hosts_policy" \
            podman kube play --replace --network "$product" build/install.yaml
        ;;
    restart)
        # A plain `podman pod restart` would copy the host's /etc/hosts lines in again.
        [[ $# -ge 2 ]] || { echo 'Usage: dev/dev.sh restart <pod>...' >&2; exit 2; }
        shift
        CONTAINERS_CONF_OVERRIDE="$hosts_policy" podman pod restart "$@"
        ;;
    down)
        # Stops what the last prepare rendered; run it before removing a component.
        podman kube down build/install.yaml
        ;;
    *) echo 'Usage: dev/dev.sh up|restart <pod>...|down' >&2; exit 2 ;;
esac
