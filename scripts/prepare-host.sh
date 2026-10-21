#!/usr/bin/env bash
# One-time setup for rootless prod. Running it again keeps the user and ID ranges.
set -euo pipefail
umask 077
# Show an explanatory host error and stop the preparation.
die() { echo "ERROR: $*" >&2; exit 1; }
# Below the home, path checks are diagnostics, not a root security boundary.
# Drop all discretionary authority before resolving any user-replaceable path.
as_service_user() {
    setpriv --reuid="$service_uid" --regid="$service_gid" --clear-groups \
        --inh-caps=-all --ambient-caps=-all --bounding-set=-all --no-new-privs -- "$@"
}
# Also used by the disposable acceptance probe; source this trusted script to
# load the functions without running host-wide setup.
prepare_service_home() {
    # The helper is embedded, not shipped as a .py file: fapolicyd's default
    # %languages rule denies every process reading an untrusted Python file, and
    # host preparation runs before any release is trusted. Bash passes a
    # here-document this small through a pipe, so no Python file is opened.
    # Python runs unprivileged and receives the code on stdin (no new RPMs).
    as_service_user python3 -B - "$service_home" <<'PREPARE_HOME' || die "Service-home preparation failed; inspect $service_home before retrying"
"""Prepare rootless directories through held descriptors, as the service user."""

import os
import stat
import sys

DIRECTORIES = (
    ".local",
    ".local/share",
    ".local/share/containers",
    ".local/share/containers/storage",
    ".config",
    ".config/cni",
    ".config/cni/net.d",
    ".config/containers",
    ".config/containers/systemd",
)
LOCK = ".config/cni/net.d/cni.lock"
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def owned_directory(descriptor, path):
    """Never repair an object owned by a different account."""
    if os.fstat(descriptor).st_uid != os.geteuid():
        raise ValueError("Inspect directory owned by another user: " + path)


def check_lock(parent, path):
    """Inspect without following links or waiting on a planted FIFO."""
    info = os.stat("cni.lock", dir_fd=parent, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
        raise ValueError("Inspect unsafe CNI lock: " + path)


def open_directories(home, descriptors, create):
    """Check all existing managed paths first; only then create missing ones."""
    for relative in DIRECTORIES:
        parent, name = os.path.split(relative)
        if parent not in descriptors:
            continue
        path = os.path.join(home, relative)
        if create:
            try:
                os.mkdir(name, mode=0o700, dir_fd=descriptors[parent])
            except FileExistsError:
                pass
        try:
            descriptor = os.open(name, DIRECTORY_FLAGS, dir_fd=descriptors[parent])
        except FileNotFoundError:
            if not create:
                continue
            raise
        descriptors[relative] = descriptor
        owned_directory(descriptor, path)


def prepare(home):
    """Create the known tree and lock without truncation or pathname chmod."""
    descriptors = {}
    try:
        descriptors[""] = os.open(home, DIRECTORY_FLAGS)
        owned_directory(descriptors[""], home)
        open_directories(home, descriptors, create=False)
        parent = os.path.dirname(LOCK)
        if parent in descriptors:
            try:
                check_lock(descriptors[parent], os.path.join(home, LOCK))
            except FileNotFoundError:
                pass
        # Reopen from the held home after preflight. O_NOFOLLOW still applies
        # if a service process replaces a checked path during preparation.
        for relative in list(descriptors):
            if relative:
                os.close(descriptors.pop(relative))
        open_directories(home, descriptors, create=True)
        for descriptor in descriptors.values():
            os.fchmod(descriptor, 0o700)
        try:
            descriptor = os.open(
                "cni.lock",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=descriptors[parent],
            )
        except FileExistsError:
            # Another process may have created it since preflight. Never unlink,
            # truncate or chmod the existing object, even in this race.
            check_lock(descriptors[parent], os.path.join(home, LOCK))
        else:
            os.close(descriptor)
    finally:
        for descriptor in descriptors.values():
            os.close(descriptor)


def main():
    if len(sys.argv) != 2 or os.geteuid() == 0:
        raise SystemExit(
            "ERROR: prepare-home requires a non-root service user and home"
        )
    try:
        prepare(sys.argv[1])
    except (OSError, ValueError) as error:
        # File paths and OS errors are useful; no application file is read.
        raise SystemExit(
            "ERROR: Unsafe or inaccessible service home; inspect it: " + str(error)
        )


if __name__ == "__main__":
    main()
PREPARE_HOME
    # Never retry these operations as root. Preserve runtime labels in storage.
    as_service_user restorecon -R -e "$container_home/storage" "$service_home" \
        || die "Service-home relabeling failed; inspect $service_home before retrying"
    as_service_user restorecon "$container_home/storage" \
        || die "Storage-directory relabeling failed; inspect $service_home before retrying"
}
if [[ ${BASH_SOURCE[0]} != "$0" ]]; then return 0; fi
[[ $EUID == 0 ]] || die "Run sudo bash scripts/prepare-host.sh --port <1024-65535> [--user <service user>]"
# Arguments: --port <1024-65535> [--user <service user>].
usage="Use --port <integer 1024-65535> [--user <service user>]"
# The service user defaults to the product name compiled into this bundle
# (product: in bundles.yaml); a standalone fixture has none and uses myproduct.
release=$(cd "$(dirname "$0")/.." && pwd)
user=myproduct
if [[ -f $release/bundle.yaml ]]; then
    # Parse the YAML: bundle.py may quote a value such as 'on'.
    user=$(python3 -c 'import sys, yaml; print(yaml.safe_load(open(sys.argv[1]))["product"])' "$release/bundle.yaml") \
        || die "Cannot read the product name from $release/bundle.yaml"
fi
port=
user_option=
while [[ $# -gt 0 ]]; do
    case $1 in
        # The required port must match HTTPS_PORT and PUBLIC_ORIGIN in config.
        --port) [[ $# -ge 2 && -z $port && $2 =~ ^[0-9]{1,5}$ ]] || die "$usage"; port=$((10#$2)); shift 2;;
        --user) [[ $# -ge 2 && -z $user_option ]] || die "$usage"; user=$2; user_option=1; shift 2;;
        *) die "$usage";;
    esac
done
[[ -n $port ]] || die "$usage"
[[ $port -ge 1024 && $port -le 65535 ]] || die "The port must be 1024-65535"
# Same rule as the product name: a portable Linux user name.
[[ $user =~ ^[a-z]([a-z0-9-]{0,30}[a-z0-9])?$ ]] || die "Invalid service user ${user@Q}; use lowercase letters, digits and inner hyphens, a letter first, at most 32 characters"
for command in python3 useradd usermod semanage restorecon loginctl firewall-cmd newuidmap newgidmap setpriv; do
    command -v "$command" >/dev/null || die "Missing $command"
done
[[ $(getenforce) == Enforcing ]] || die "SELinux must be Enforcing"
firewall-cmd --state || die "firewalld must be running"
# fapolicyd: a small subject cache evicts processes while they start, and its
# ld.so pattern rule can then deny systemd's launch of Podman (203/EXEC). The
# setting belongs to the host's security baseline, so only warn (README).
fapolicyd_conf=/etc/fapolicyd/fapolicyd.conf
if [[ -r $fapolicyd_conf ]]; then
    subj_cache=$(sed -n 's/^[[:space:]]*subj_cache_size[[:space:]]*=[[:space:]]*\([0-9][0-9]*\)[[:space:]]*$/\1/p' "$fapolicyd_conf" | tail -n 1)
    if [[ -z $subj_cache || $subj_cache -lt 16381 ]]; then
        echo "WARNING: fapolicyd subj_cache_size is ${subj_cache:-unset}; set it to 16381 in $fapolicyd_conf and restart fapolicyd before installing (see README)" >&2
    fi
fi
service_home=/var/lib/$user
# Check the trusted anchor before useradd can create anything beneath it.
[[ ! -L /var/lib && -d /var/lib && $(stat -c %u /var/lib) == 0 && $(stat -c %a /var/lib) =~ ^[57][015][015]$ ]] \
    || die "/var/lib must be a root-owned directory without group/other write access"
if ! getent passwd "$user" >/dev/null; then
    useradd --system --create-home --home-dir "$service_home" --shell /sbin/nologin "$user"
fi
# An existing account is never redefined and its data is never moved.
[[ $(getent passwd "$user" | cut -d: -f6) == "$service_home" ]] || die "$user must have home $service_home"
[[ $(getent passwd "$user" | cut -d: -f7) == /sbin/nologin ]] || die "$user must have shell /sbin/nologin"
service_uid=$(id -u "$user")
service_gid=$(id -g "$user")
[[ $service_uid != 0 && $service_gid != 0 ]] || die "The service account must not use root UID or GID"
# /var/lib is the root-controlled anchor. The service user cannot replace this
# final home entry; descendants remain untrusted even after a successful check.
[[ ! -L $service_home && -d $service_home ]] || die "Inspect non-directory or symlink home $service_home"
[[ $(stat -c %u "$service_home") == "$service_uid" ]] || die "The home $service_home must be owned by $user"
chmod 0700 "$service_home"
# Keep ID mappings for existing volumes; users must not overlap.
read -r uid_range gid_range < <(python3 - "$user" <<'PY'
import sys
from pathlib import Path
user = sys.argv[1]
rows = []
for name in ("subuid", "subgid"):
    entries = []
    for line in Path("/etc/" + name).read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        owner, start, count = line.split(":")
        entries.append((owner, int(start), int(start) + int(count) - 1))
    rows.append(entries)
next_id = max([100000] + [end + 1 for entries in rows for _, _, end in entries])
if next_id + 65535 > 4294967294:
    raise SystemExit("ERROR: No free subuid/subgid block")
result = []
for entries in rows:
    own = [(start, end) for owner, start, end in entries if owner == user]
    if own:
        if not any(end - start + 1 >= 65536 for start, end in own):
            raise SystemExit("ERROR: " + user + " needs at least 65536 subordinate IDs")
        for start, end in own:
            if any(owner != user and start <= other_end and other_start <= end
                   for owner, other_start, other_end in entries):
                raise SystemExit("ERROR: Overlap in subuid/subgid")
        result.append("existing")
    else:
        result.append("{}-{}".format(next_id, next_id + 65535))
print(" ".join(result))
PY
)
[[ $uid_range == existing ]] || usermod --add-subuids "$uid_range" "$user"
[[ $gid_range == existing ]] || usermod --add-subgids "$gid_range" "$user"
# SELinux: storage needs its own equivalence because system users lack HOME_DIR rules.
equivalences=$(semanage fcontext -l -C)
container_home="$service_home/.local/share/containers"
expected="$container_home = /var/lib/containers"
while IFS= read -r equivalence; do
    if [[ $equivalence == "$service_home"*' = '* && $equivalence != "$expected" ]]; then
        die "Unexpected SELinux equivalence: $equivalence. Remove it manually before preparing"
    fi
done <<< "$equivalences"
if ! grep -Fqx "$expected" <<< "$equivalences"; then
    semanage fcontext -a -e /var/lib/containers "$container_home"
fi
# Pre-create directories/lock so Podman does not create them with a runtime type.
prepare_service_home
loginctl enable-linger "$user"
firewall-cmd --permanent --add-port="$port/tcp"
firewall-cmd --reload
printf '[OK] service user %s: home %s (0700), linger enabled, HTTPS port %s/tcp open\n' "$user" "$service_home" "$port"
