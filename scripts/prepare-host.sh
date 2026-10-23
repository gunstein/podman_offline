#!/usr/bin/env bash
# Prepare an existing login account to run one product rootless, with every
# product file under the root-owned /var/lib/<product> (backlog 64). Running it
# again keeps the account, its home, ID ranges and populated storage.
set -euo pipefail
umask 077
# Show an explanatory host error and stop the preparation.
die() { echo "ERROR: $*" >&2; exit 1; }
# Below the account's directories, path checks are diagnostics, not a root
# security boundary. Drop all discretionary authority before resolving any
# user-replaceable path.
as_service_user() {
    setpriv --reuid="$service_uid" --regid="$service_gid" --clear-groups \
        --inh-caps=-all --ambient-caps=-all --bounding-set=-all --no-new-privs -- "$@"
}
# Also used by the disposable acceptance probe; source this trusted script to
# load the functions without running host-wide setup.
prepare_install_directories() {
    # The helper is embedded, not shipped as a .py file: fapolicyd's default
    # %languages rule denies every process reading an untrusted Python file, and
    # host preparation runs before any release is trusted. Bash passes a
    # here-document this small through a pipe, so no Python file is opened.
    # Python runs unprivileged and receives the code on stdin (no new RPMs).
    as_service_user python3 -B - "$install_root" <<'PREPARE_HOME' || die "Installation directory preparation failed; inspect $install_root before retrying"
"""Prepare the account's directories through held descriptors, as that account.

The installation root is root-owned and was checked by the caller, which also
created state/, config/ and storage/ for the account; the account cannot replace
them. config/ and storage/ are XDG_CONFIG_HOME and XDG_DATA_HOME for Podman.
"""

import os
import stat
import sys

DIRECTORIES = (
    "state",
    "config",
    "config/cni",
    "config/cni/net.d",
    "config/containers",
    "config/containers/systemd",
    "storage",
    "storage/containers",
    "storage/containers/storage",
)
LOCK = "config/cni/net.d/cni.lock"
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
        # The root-owned root itself is never changed here.
        descriptors[""] = os.open(home, DIRECTORY_FLAGS)
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
        for relative, descriptor in descriptors.items():
            if relative:
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
            "ERROR: prepare-home requires a non-root account and installation root"
        )
    try:
        prepare(sys.argv[1])
    except (OSError, ValueError) as error:
        # File paths and OS errors are useful; no application file is read.
        raise SystemExit(
            "ERROR: Unsafe or inaccessible installation directory; inspect it: "
            + str(error)
        )


if __name__ == "__main__":
    main()
PREPARE_HOME
    # Never retry these operations as root. Preserve runtime labels in storage.
    as_service_user restorecon -R -e "$container_home/storage" "$install_root/state" "$install_root/config" "$install_root/storage" \
        || die "Installation directory relabeling failed; inspect $install_root before retrying"
    as_service_user restorecon "$container_home/storage" \
        || die "Storage-directory relabeling failed; inspect $install_root before retrying"
}
if [[ ${BASH_SOURCE[0]} != "$0" ]]; then return 0; fi
[[ $EUID == 0 ]] || die "Run sudo bash scripts/prepare-host.sh --port <1024-65535> --user <existing account>"
# Arguments: --port <1024-65535> --user <existing account>.
usage="Use --port <integer 1024-65535> --user <existing login account>"
# The product name is compiled into this bundle (product: in bundles.yaml); a
# standalone fixture has none and uses myproduct. It names the installation
# root; the account is chosen explicitly and need not match it.
release=$(cd "$(dirname "$0")/.." && pwd)
product=myproduct
if [[ -f $release/bundle.yaml ]]; then
    # Parse the YAML: bundle.py may quote a value such as 'on'.
    product=$(python3 -I -c 'import sys, yaml; print(yaml.safe_load(open(sys.argv[1]))["product"])' "$release/bundle.yaml") \
        || die "Cannot read the product name from $release/bundle.yaml"
fi
port=
user=
while [[ $# -gt 0 ]]; do
    case $1 in
        # The required port must match HTTPS_PORT and PUBLIC_ORIGIN in config.
        --port) [[ $# -ge 2 && -z $port && $2 =~ ^[0-9]{1,5}$ ]] || die "$usage"; port=$((10#$2)); shift 2;;
        --user) [[ $# -ge 2 && -z $user ]] || die "$usage"; user=$2; shift 2;;
        *) die "$usage";;
    esac
done
[[ -n $port && -n $user ]] || die "$usage"
[[ $port -ge 1024 && $port -le 65535 ]] || die "The port must be 1024-65535"
# A portable Linux user name, as for the product name.
[[ $user =~ ^[A-Za-z_][A-Za-z0-9_.-]{0,31}$ ]] || die "Invalid account name ${user@Q}; use an existing login name"
[[ $product =~ ^[a-z]([a-z0-9-]{0,30}[a-z0-9])?$ ]] || die "Invalid product name in $release/bundle.yaml"
for command in python3 semanage restorecon loginctl firewall-cmd newuidmap newgidmap setpriv systemctl usermod getfacl; do
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
# The account must already exist; its home, shell and login stay unchanged.
getent passwd "$user" >/dev/null || die "Account $user does not exist; create it with the organisation's normal procedure first"
service_uid=$(id -u "$user")
service_gid=$(id -g "$user")
[[ $service_uid != 0 && $service_gid != 0 ]] || die "The account must not use root UID or GID"
account_home=$(getent passwd "$user" | cut -d: -f6)
install_root=/var/lib/$product
container_home=$install_root/storage/containers
# Check the trusted anchor and the root before creating anything beneath them.
[[ ! -L /var/lib && -d /var/lib && $(stat -c %u /var/lib) == 0 && $(stat -c %a /var/lib) =~ ^[57][015][015]$ ]] \
    || die "/var/lib must be a root-owned directory without group/other write access"
if [[ ! -e $install_root && ! -L $install_root ]]; then
    mkdir -m 0755 "$install_root"
fi
[[ ! -L $install_root && -d $install_root && $(stat -c %u "$install_root") == 0 && $(stat -c %a "$install_root") == 755 ]] \
    || die "$install_root must be a root-owned directory with mode 0755; inspect it (an old service-home installation is not migrated)"
[[ -z $(getfacl --absolute-names --skip-base -- "$install_root" 2>/dev/null) ]] \
    || die "Remove the ACL on $install_root"
# One account per product and one product per account; never take over another's state.
for name in state config storage; do
    path=$install_root/$name
    if [[ -e $path || -L $path ]]; then
        [[ ! -L $path && -d $path && $(stat -c %u "$path") == "$service_uid" ]] \
            || die "$path belongs to another account or is not a directory; inspect it"
    fi
done
dropin_dir=/etc/systemd/system/user@$service_uid.service.d
dropin=$dropin_dir/podman-offline-$product.conf
for other in "$dropin_dir"/podman-offline-*.conf; do
    [[ ! -e $other || $other == "$dropin" ]] || die "$user already runs another product ($other); use a separate account per product"
done
# The root creates the account's directories directly under the root-owned
# root; the account cannot replace these entries, so chown/chmod are safe here.
for name in state config storage; do
    path=$install_root/$name
    if [[ ! -e $path ]]; then
        mkdir -m 0700 "$path"
        chown -h "$service_uid:$service_gid" "$path"
    fi
    chmod 0700 "$path"
done
# Keep ID mappings for existing volumes; users must not overlap.
read -r uid_range gid_range < <(python3 -I - "$user" <<'PY'
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
# SELinux: Podman storage under /var/lib/<product> needs the container labels.
equivalences=$(semanage fcontext -l -C)
expected="$container_home = /var/lib/containers"
while IFS= read -r equivalence; do
    if [[ $equivalence == "$install_root"*' = '* && $equivalence != "$expected" ]]; then
        die "Unexpected SELinux equivalence: $equivalence. Remove it manually before preparing"
    fi
done <<< "$equivalences"
if ! grep -Fqx "$expected" <<< "$equivalences"; then
    semanage fcontext -a -e /var/lib/containers "$container_home"
fi
# Pre-create directories/lock so Podman does not create them with a runtime type.
prepare_install_directories
# The user's systemd manager, its Quadlet generator and every service started
# at boot get Podman's config and storage from these two variables. A terminal
# export cannot reach them; this root-owned drop-in is the one persistent place.
dropin_text="# Managed by podman-offline scripts/prepare-host.sh for product $product.
[Service]
Environment=XDG_CONFIG_HOME=$install_root/config XDG_DATA_HOME=$install_root/storage
"
if [[ -e $dropin || -L $dropin ]]; then
    [[ ! -L $dropin && -f $dropin && $(cat "$dropin") == "${dropin_text%$'\n'}" ]] \
        || die "$dropin differs from the expected settings; inspect and remove it manually (a changed installation root is not migrated)"
else
    install -d -m 0755 "$dropin_dir"
    printf '%s' "$dropin_text" > "$dropin.tmp"
    chmod 0644 "$dropin.tmp"
    mv -f "$dropin.tmp" "$dropin"
fi
systemctl daemon-reload
loginctl enable-linger "$user"
# Decide from the running manager, not from whether this run wrote the file:
# a run interrupted after writing it must still be activated by a repeat.
manager_has_settings() {
    local environment
    environment=$(systemctl --user -M "$user@" show-environment) || return 1
    grep -Fqx "XDG_CONFIG_HOME=$install_root/config" <<< "$environment" \
        && grep -Fqx "XDG_DATA_HOME=$install_root/storage" <<< "$environment"
}
if ! systemctl is-active --quiet "user@$service_uid.service"; then
    systemctl start "user@$service_uid.service"
elif ! manager_has_settings; then
    # A running manager keeps its old environment until it restarts.
    echo "Restarting user@$service_uid.service so it uses $install_root" >&2
    systemctl restart "user@$service_uid.service"
fi
manager_has_settings \
    || die "user@$service_uid.service does not use $install_root/config and $install_root/storage; inspect 'systemctl cat user@$service_uid.service' and retry"
firewall-cmd --permanent --add-port="$port/tcp"
firewall-cmd --reload
printf '[OK] account %s (home %s unchanged): product %s under %s, linger enabled, HTTPS port %s/tcp open\n' \
    "$user" "$account_home" "$product" "$install_root" "$port"
printf '[OK] next, as %s: create %s/.%s/%s.env (0700/0600) with INSTALL_ROOT=%s\n' \
    "$user" "$account_home" "$product" "$product" "$install_root"
