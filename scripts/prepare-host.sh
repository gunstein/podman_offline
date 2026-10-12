#!/usr/bin/env bash
# Engangsoppsett for rootless prod. Gjentatt kjøring beholder bruker og ID-områder.
set -euo pipefail
umask 077
if [[ $EUID != 0 ]]; then
    echo 'ERROR: Kjør sudo bash scripts/prepare-host.sh [config.yaml]' >&2
    exit 1
fi
root=$(cd "$(dirname "$0")/.." && pwd)
config=${1:-$root/config.yaml}
[[ -f $config ]] || config="$root/config.example.yaml"
for command in python3 useradd usermod semanage restorecon loginctl firewall-cmd newuidmap newgidmap; do
    command -v "$command" >/dev/null || { echo "ERROR: Mangler $command" >&2; exit 1; }
done
# Les config som root før vi endrer verten. Ingen produktkode importeres/trustes.
port=$(python3 - "$config" <<'PY'
import sys, yaml
with open(sys.argv[1]) as stream:
    port = yaml.safe_load(stream).get("HTTPS_PORT")
if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
    raise SystemExit("ERROR: Rootless HTTPS_PORT må være et heltall 1024-65535")
print(port)
PY
)
[[ $(getenforce) == Enforcing ]]
firewall-cmd --state
service_home=/var/lib/myproduct
if ! getent passwd myproduct >/dev/null; then
    useradd --system --create-home --home-dir "$service_home" --shell /sbin/nologin myproduct
fi
# Avvis en annen eksisterende konto; ikke endre hjem/shell/eierskap rekursivt.
[[ $(getent passwd myproduct | cut -d: -f6) == "$service_home" ]]
[[ $(getent passwd myproduct | cut -d: -f7) == /sbin/nologin ]]
[[ $(stat -c %u "$service_home") == "$(id -u myproduct)" ]]
chmod 0700 "$service_home"
# Behold gyldige eksisterende områder. Velg ett ledig område i begge navnerom.
# Kun manglende tildelinger skrives; overlapp eller for små områder gir stopp.
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
# Persistér samme policyoppslag som /home. Eksisterende identisk regel beholdes.
equivalences=$(semanage fcontext -l -C)
if ! grep -Fqx "$service_home = /home" <<< "$equivalences"; then
    semanage fcontext -a -e /home "$service_home"
fi
restorecon -R "$service_home"
loginctl enable-linger myproduct
firewall-cmd --permanent --add-port="$port/tcp"
firewall-cmd --reload
printf '[OK] myproduct: hjem %s (0700), linger aktiv, HTTPS-port %s/tcp åpen\n' "$service_home" "$port"
