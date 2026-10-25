#!/usr/bin/env bash
# WP0 investigation fixtures only. All keys and artifacts stay outside Git.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
work=$1
bundles=$2
mkdir -p "$work/source/rpm-prototype" "$work/source/scripts" "$work/key"
# Never mount the original signing home in a container or run gpg against it.
# Agent sockets are deliberately excluded from this disposable copy.
cp -a "$HOME/.podman-offline-rpm-gnupg/private-keys-v1.d" "$work/key/"
cp "$HOME/.podman-offline-rpm-gnupg/pubring.kbx" "$work/key/"
chmod 0700 "$work/key"
cp "$root"/rpm-prototype/*.sh "$work/source/rpm-prototype/"
cp "$root/scripts/prepare-host.sh" "$work/source/scripts/"
RPM_KEY_HOME="$work/key" TOOLS_VERSION=0.202610250832 \
    bash "$work/source/rpm-prototype/build-rpms.sh" \
    "$bundles/myproduct-platform-0.4.12-offline.tar.gz" \
    "$bundles/myproduct-identity-0.4.12-offline.tar.gz" \
    "$bundles/myproduct-platform-0.4.13-offline.tar.gz"
mkdir "$work/fixtures"
cp "$work/source/dist/rpm/"* "$work/fixtures/"
# Relabel only disposable copies, never the repository on an SELinux host.
cp -a "$here" "$work/support"
podman run --rm -v "$work/key":/key:Z -v "$work/fixtures":/out:Z \
    -v "$work/support":/support:ro,Z \
    -v "$work/support/signatures.sh":/fixtures.sh:ro,Z \
    docker.io/library/oraclelinux:9 bash /fixtures.sh
