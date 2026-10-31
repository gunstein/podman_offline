#!/usr/bin/env bash
# Lab prototype (backlog 69): wrap built offline bundles as signed RPMs.
#
# Usage: rpm-prototype/build-rpms.sh <product>-<component>-<version>-offline.tar.gz...
#
# Runs on a machine with Podman and network access (the build container
# installs rpm-build). Writes dist/rpm/: one RPM per bundle, named
# <product>-<component>-<version> so versions install side by side, one
# <product>-host-tools RPM with the host setup command, and the public key
# RPM-GPG-KEY-<product>. Each RPM installs its release unchanged under
# /var/lib/<product>/releases/<product>-<component>-<version>/, where the
# product expects published releases; fapolicyd trusts the files through the
# RPM database. Not a product feature; see acceptance/RPM-PROTOTYPE.md in the git history.
set -euo pipefail

usage() {
    echo "Usage: rpm-prototype/build-rpms.sh <product>-<component>-<version>-offline.tar.gz..." >&2
    exit 2
}
[[ $# -gt 0 ]] || usage
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/.." && pwd)
out=$root/dist/rpm
# A lab-only signing key, kept outside the checkout. Production would use the
# supplier's own RPM signing key instead.
key_home=${RPM_KEY_HOME:-$HOME/.podman-offline-rpm-gnupg}
image=${RPM_BUILD_IMAGE:-docker.io/library/oraclelinux:9}
command -v podman >/dev/null || { echo "ERROR: podman is required" >&2; exit 1; }

inputs=$(mktemp -d)
trap 'rm -rf "$inputs"' EXIT
for archive in "$@"; do
    name=$(basename "$archive")
    [[ -f $archive && $name =~ ^[a-z][a-z0-9-]*-[0-9]+\.[0-9]+\.[0-9]+-offline\.tar\.gz$ ]] \
        || { echo "ERROR: not a bundle archive: $archive" >&2; exit 1; }
    if [[ -f $archive.sha256 ]]; then
        (cd "$(dirname "$archive")" && sha256sum -c --quiet "$name.sha256") \
            || { echo "ERROR: checksum mismatch for $archive" >&2; exit 1; }
    fi
    cp "$archive" "$inputs/"
done
cp "$root/scripts/prepare-host.sh" "$here/host-setup.sh" "$here/build-inside.sh" "$inputs/"
mkdir -p "$out"
install -d -m 0700 "$key_home"

podman run --rm \
    -v "$inputs":/in:ro,Z \
    -v "$out":/out:Z \
    -v "$key_home":/key:Z \
    -e TOOLS_VERSION="${TOOLS_VERSION:-0.$(date -u +%Y%m%d%H%M)}" \
    "$image" bash /in/build-inside.sh
echo "Wrote $out"
