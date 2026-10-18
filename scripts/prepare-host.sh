#!/usr/bin/env bash
# One-time setup for rootless prod. Running it again keeps the user and ID ranges.
set -euo pipefail
umask 077
# Show an explanatory host error and stop the preparation.
die() { echo "ERROR: $*" >&2; exit 1; }
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
for command in python3 useradd usermod semanage restorecon loginctl firewall-cmd newuidmap newgidmap install; do
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
if ! getent passwd "$user" >/dev/null; then
    useradd --system --create-home --home-dir "$service_home" --shell /sbin/nologin "$user"
fi
# An existing account is never redefined and its data is never moved.
[[ $(getent passwd "$user" | cut -d: -f6) == "$service_home" ]] || die "$user must have home $service_home"
[[ $(getent passwd "$user" | cut -d: -f7) == /sbin/nologin ]] || die "$user must have shell /sbin/nologin"
[[ $(stat -c %u "$service_home") == "$(id -u "$user")" ]] || die "The home $service_home must be owned by $user"
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
# Creating these first stops Podman from creating config directories with a runtime type.
for directory in .local .local/share .local/share/containers .local/share/containers/storage \
    .config .config/cni .config/cni/net.d .config/containers .config/containers/systemd; do
    install -d -m 0700 -o "$user" -g "$(id -gn "$user")" "$service_home/$directory"
done
# The CNI lock is also opened during backend initialization. Create it first without
# truncating an existing lock, so Podman does not create it with a runtime type.
if [[ ! -e $service_home/.config/cni/net.d/cni.lock ]]; then
    install -m 0600 -o "$user" -g "$(id -gn "$user")" /dev/null "$service_home/.config/cni/net.d/cni.lock"
fi
# Podman's runtime labels in populated storage must survive a repeated preparation.
restorecon -R -e "$container_home/storage" "$service_home"
restorecon "$container_home/storage"
loginctl enable-linger "$user"
firewall-cmd --permanent --add-port="$port/tcp"
firewall-cmd --reload
printf '[OK] service user %s: home %s (0700), linger enabled, HTTPS port %s/tcp open\n' "$user" "$service_home" "$port"
