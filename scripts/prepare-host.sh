#!/usr/bin/env bash
# Engangsoppsett for rootless prod. Gjentatt kjøring beholder bruker og ID-områder.
set -euo pipefail
umask 077
# Vis en forklarende vertsfeil og stopp klargjøringen.
die() { echo "ERROR: $*" >&2; exit 1; }
[[ $EUID == 0 ]] || die "Kjør sudo bash scripts/prepare-host.sh --port <1024-65535>"
# Påkrevd port må være identisk med HTTPS_PORT og PUBLIC_ORIGIN i config.
[[ $# == 2 && ${1:-} == --port && ${2:-} =~ ^[0-9]{1,5}$ ]] || die "Bruk --port <heltall 1024-65535>"
port=$((10#$2))
[[ $port -ge 1024 && $port -le 65535 ]] || die "Porten må være 1024-65535"
for command in python3 useradd usermod semanage restorecon loginctl firewall-cmd newuidmap newgidmap install; do
    command -v "$command" >/dev/null || die "Mangler $command"
done
[[ $(getenforce) == Enforcing ]] || die "SELinux må være Enforcing"
firewall-cmd --state || die "firewalld må kjøre"
service_home=/var/lib/myproduct
if ! getent passwd myproduct >/dev/null; then
    useradd --system --create-home --home-dir "$service_home" --shell /sbin/nologin myproduct
fi
# En eksisterende konto skal ikke omdefineres eller få data flyttet.
[[ $(getent passwd myproduct | cut -d: -f6) == "$service_home" ]] || die "myproduct må ha hjem $service_home"
[[ $(getent passwd myproduct | cut -d: -f7) == /sbin/nologin ]] || die "myproduct må ha shell /sbin/nologin"
[[ $(stat -c %u "$service_home") == "$(id -u myproduct)" ]] || die "Hjemmet $service_home må være eid av myproduct"
chmod 0700 "$service_home"
# Bevar ID-mappinger for eksisterende volumer; brukere må ikke ha overlapp.
read -r uid_range gid_range < <(python3 - <<'PY'
from pathlib import Path
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
    raise SystemExit("ERROR: Ingen ledig subuid/subgid-blokk")
result = []
for entries in rows:
    own = [(start, end) for owner, start, end in entries if owner == "myproduct"]
    if own:
        if not any(end - start + 1 >= 65536 for start, end in own):
            raise SystemExit("ERROR: myproduct trenger minst 65536 underordnede ID-er")
        for start, end in own:
            if any(owner != "myproduct" and start <= other_end and other_start <= end
                   for owner, other_start, other_end in entries):
                raise SystemExit("ERROR: Overlapp i subuid/subgid")
        result.append("existing")
    else:
        result.append("{}-{}".format(next_id, next_id + 65535))
print(" ".join(result))
PY
)
[[ $uid_range == existing ]] || usermod --add-subuids "$uid_range" myproduct
[[ $gid_range == existing ]] || usermod --add-subgids "$gid_range" myproduct
# SELinux: lageret trenger egen ekvivalens fordi systembrukere mangler HOME_DIR.
equivalences=$(semanage fcontext -l -C)
container_home="$service_home/.local/share/containers"
expected="$container_home = /var/lib/containers"
while IFS= read -r equivalence; do
    if [[ $equivalence == "$service_home"*' = '* && $equivalence != "$expected" ]]; then
        die "Uventet SELinux-ekvivalens: $equivalence. Fjern den manuelt før klargjøring"
    fi
done <<< "$equivalences"
if ! grep -Fqx "$expected" <<< "$equivalences"; then
    semanage fcontext -a -e /var/lib/containers "$container_home"
fi
# Preoppretting hindrer at Podman lager config-kataloger med runtime-type.
for directory in .local .local/share .local/share/containers .local/share/containers/storage \
    .config .config/cni .config/cni/net.d .config/containers .config/containers/systemd; do
    install -d -m 0700 -o myproduct -g "$(id -gn myproduct)" "$service_home/$directory"
done
# CNI-låsen åpnes også ved backend-initialisering. Preopprett uten å avkorte
# en eksisterende lås, så Podman ikke oppretter den med runtime-type.
if [[ ! -e $service_home/.config/cni/net.d/cni.lock ]]; then
    install -m 0600 -o myproduct -g "$(id -gn myproduct)" /dev/null "$service_home/.config/cni/net.d/cni.lock"
fi
# Podmans runtime-labels i et fylt lager må bevares ved ny klargjøring.
restorecon -R -e "$container_home/storage" "$service_home"
restorecon "$container_home/storage"
loginctl enable-linger myproduct
firewall-cmd --permanent --add-port="$port/tcp"
firewall-cmd --reload
printf '[OK] myproduct: hjem %s (0700), linger aktiv, HTTPS-port %s/tcp åpen\n' "$service_home" "$port"
