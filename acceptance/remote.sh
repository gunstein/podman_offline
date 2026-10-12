#!/usr/bin/env bash
# Kjør faste akseptansesteg på VM-ene uten å logge hemmeligheter.
set -euo pipefail
action=$1
run=$2
lab=$3
prod_ip=$4
prod_host=$5
port=$6
revision=$7
role=$8
run_started=$9
requested_version=${10:-}
state=/var/lib/myproduct
base="$HOME/podman-offline-acceptance/$run"
src="$base/src"
product="/var/lib/myproduct/releases/myproduct-RELEASE"
if [[ -f $base/version ]]; then product="/var/lib/myproduct/releases/myproduct-$(cat "$base/version")"; fi
private="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/podman-offline-$run"
# Kjør kommandoer som tjenestebrukeren fra hjemmet med riktig runtime.
as_product() {
    sudo -n -H -u myproduct bash -c '
        cd "$HOME" || exit
        export XDG_RUNTIME_DIR="/run/user/$(id -u)"
        exec "$@"
    ' bash "$@"
}
# Styr produktets tjeneste i tjenestebrukerens systemd-instans.
user_service() { sudo -n systemctl --user -M myproduct@ "$@"; }
# Samle audit med adskilte strømmer og godta bare det dokumenterte tomme svaret.
audit_events() {
    sudo -n python3 - "$start_date" "$start_time" "$1" <<'AUDIT'
import os
import subprocess
import sys


def collect():
    """Logg audit-strømmene og avvis feil eller avvisninger i kontrollmodus."""
    result = subprocess.run(
        ["ausearch", "--input-logs", "-m", "FANOTIFY,AVC,USER_AVC", "-ts",
         sys.argv[1], sys.argv[2], "-i"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
        check=False, env=dict(os.environ, LC_ALL="C"))
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    if result.returncode == 1 and not result.stdout.strip() and result.stderr.strip() == "<no matches>":
        print("PASS: no FANOTIFY/AVC events since run start")
        return
    if result.returncode or not result.stdout.strip():
        raise SystemExit("FAIL: audit lookup failed or returned empty stdout")
    if sys.argv[3] == "check":
        raise SystemExit("FAIL: FANOTIFY/AVC events recorded since run start")


collect()
AUDIT
}
# Valider VM-rollens fapolicyd-, SELinux- og firewalld-profil.
profile() {
    selinux=$(getenforce)
    firewall=$(systemctl show firewalld -p ActiveState --value)
    policy=$(systemctl show fapolicyd -p ActiveState --value)
    enabled=$(systemctl show fapolicyd -p UnitFileState --value)
    printf 'PROFILE %s fapolicyd=%s unit=%s SELinux=%s firewalld=%s\n' "$role" "$policy" "$enabled" "$selinux" "$firewall"
    test "$selinux" = Enforcing
    test "$firewall" = active
    if [[ $role == DEV ]]; then
        test "$policy" = inactive
        test "$enabled" = disabled
    else
        test "$role" = PROD
        test "$policy" = active
    fi
}
# Logg OS-, verktøy- og oppstartsdata etter profilkontroll.
facts() {
    profile
    cat /etc/os-release
    podman --version
    systemctl --version
    python3 -c 'import yaml; print("PyYAML", yaml.__version__)'
    printf 'boot_id='; cat /proc/sys/kernel/random/boot_id
    getenforce
    test "$(getenforce)" = Enforcing
    sudo -n systemctl is-active firewalld
    df -h "$HOME"
}
# Bekreft blokkert internett uten å godta manglende verktøy som nettbevis.
offline() {
    sudo -n systemctl is-active podman-offline-isolation.service
    sudo -n nft list table inet podman_offline
    # Require the expected network failure, never missing tools, auth errors or success.
    if curl --noproxy '*' -m5 -sS https://registry-1.docker.io/v2/; then
        echo 'FAIL: registry reachable'; exit 1
    else
        status=$?
        case "$status" in 5|6|7|28) echo "PASS: registry blocked (exit $status)";;
            *) echo "FAIL: unexpected curl exit $status"; exit 1;; esac
    fi
    python3 - <<'PY'
import socket
socket.setdefaulttimeout(5)
try:
    socket.getaddrinfo("registry-1.docker.io", 443)
except socket.gaierror:
    print("PASS: public DNS lookup failed")
else:
    raise SystemExit("FAIL: public DNS resolved")
PY
    # Check prerequisites separately: a missing binary is not proof of isolation.
    sudo -n podman version >/dev/null
    if timeout 20 sudo -n podman pull docker.io/library/busybox | sed 's/^/pull-probe: /'; then
        echo 'FAIL: public image pulled'; exit 1
    else
        status=$?
        test "$status" = 125 -o "$status" = 124
        echo "PASS: public pull failed (exit $status)"
    fi
}
# Kontroller aktiv tjeneste og alle forventede appcontainere.
healthy() {
    user_service is-active myproduct.service
    as_product podman ps --all --pod
    as_product podman ps -a --format json | python3 -c '
import json, sys
rows = json.load(sys.stdin)
names = ("myproduct-identity-postgres-db", "myproduct-todo-postgres-db",
         "myproduct-identity-app", "myproduct-todo-backend",
         "myproduct-todo-frontend", "myproduct-help-web", "myproduct-proxy-nginx")
for name in names:
    found = [c for c in rows if name in c["Names"]]
    assert len(found) == 1 and found[0]["State"] == "running", name
print("PASS: all seven application containers running")'
}
case "$action" in
readiness)
    profile
    for command in bash podman python3 openssl curl tar sha256sum timeout; do command -v "$command"; done
    sudo -n true
    python3 -c 'import yaml'
    test -d "${XDG_RUNTIME_DIR:?}"
    test -w "$XDG_RUNTIME_DIR"
    ;;
clean)
    facts
    for prefix in '' 'sudo -n'; do
        output=$($prefix podman ps -aq)
        test -z "$output"
        output=$($prefix podman pod ps -q)
        test -z "$output"
        output=$($prefix podman volume ls -q)
        test -z "$output"
        output=$($prefix podman secret ls -q)
        test -z "$output"
        $prefix podman images --format '{{.Repository}}:{{.Tag}}'
    done
    output=$(sudo -n find /etc/containers/systemd -maxdepth 1 -name 'myproduct.*' -print)
    test -z "$output"
    if [[ $role == PROD ]]; then
        if getent passwd myproduct; then echo 'FAIL: myproduct user already exists'; exit 1; fi
        sudo -n test ! -e /var/lib/myproduct
    fi
    test ! -e "$base"
    ;;
isolate)
    command -v nft
    # Separate persistent nft table; firewalld remains enabled.
    sudo -n tee /etc/podman-offline-isolation.nft >/dev/null <<NFT
table inet podman_offline {
 chain input {
  type filter hook input priority -200; policy drop;
  iifname "lo" accept
  ct state established,related accept
  iifname "podman*" udp dport 53 accept
  iifname "podman*" tcp dport 53 accept
  ip saddr $lab tcp dport { 22, $port } accept
 }
 chain output {
  type filter hook output priority -200; policy drop;
  oifname "lo" accept
  oifname "podman*" accept
  udp dport 53 reject
  tcp dport 53 reject
  ip daddr $lab accept
 }
 chain forward {
  type filter hook forward priority -200; policy drop;
  iifname "podman*" oifname "podman*" accept
  ip saddr $lab oifname "podman*" tcp dport $port accept
  ip daddr $lab accept
 }
}
NFT
    sudo -n tee /etc/systemd/system/podman-offline-isolation.service >/dev/null <<'UNIT'
[Unit]
Description=Acceptance offline isolation
DefaultDependencies=no
After=local-fs.target
Before=network-pre.target firewalld.service
Wants=network-pre.target
[Service]
Type=oneshot
ExecStart=/usr/sbin/nft -f /etc/podman-offline-isolation.nft
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
UNIT
    sudo -n systemctl daemon-reload
    sudo -n systemctl enable --now podman-offline-isolation.service
    offline
    ;;
offline) offline;;
clone)
    command -v git
    git clone "$base/source.bundle" "$src"
    cd "$src"
    git checkout --detach "$revision"
    output=$(git status --porcelain)
    test -z "$output"
    git rev-parse HEAD
    cat VERSION
    ;;
unit) cd "$src"; python3 -m unittest discover -s tests;;
build-images) cd "$src"; ./dev/build-images.sh;;
dev-up)
    cd "$src"
    ./scripts/generate-certificates.sh
    cp config.example.yaml config.yaml
    chmod 600 config.yaml
    ./dev/dev.sh up
    ;;
venv)
    cd "$src"
    python3 -m venv .venv-smoke
    .venv-smoke/bin/pip install -r apps/todo-backend/requirements.txt
    ;;
dev-e2e) cd "$src"; .venv-smoke/bin/python dev/smoke-test.py;;
examples-setup)
    podman pull docker.io/library/busybox:1.37.0
    podman tag docker.io/library/busybox:1.37.0 localhost/offline-example:1
    ;;
example-*) cd "$src"; ./examples/run.sh "${action#example-}";;
dev-down) cd "$src"; ./dev/dev.sh down;;
bundle)
    cd "$src"
    output=$(git status --porcelain)
    test -z "$output"
    ./build-bundle.sh
    cd dist
    sha256sum -c ./*.sha256
    cd ..
    cat build/bundle/myproduct-*/images/images.txt
    ;;
upgrade-bundle)
    cd "$src"
    output=$(git status --porcelain)
    test -z "$output"
    [[ $requested_version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
    printf '%s\n' "$requested_version" > VERSION
    changed=$(git diff --name-only)
    test "$changed" = VERSION
    git diff -- VERSION
    ./build-bundle.sh
    (cd dist && sha256sum -c "myproduct-$requested_version-offline.tar.gz.sha256")
    cat "build/bundle/myproduct-$requested_version/images/images.txt"
    ;;
upgrade)
    cd "$base"
    archive="myproduct-$(cat version)-offline.tar.gz"
    sha256sum -c "$archive.sha256"
    # shellcheck disable=SC2024
    sudo -n -H -u myproduct tar xzf - -C /var/lib/myproduct/releases < "$archive"
    sudo -n bash -c 'cd "$1" && sha256sum -c --quiet checksums.sha256' bash "$product"
    sudo -n fapolicyd-cli --file add "$product/deploy.py" --trust-file myproduct
    old_release="/var/lib/myproduct/releases/myproduct-$requested_version"
    sudo -n fapolicyd-cli --file delete "$old_release/deploy.py" --trust-file myproduct
    sudo -n fapolicyd-cli --update
    sudo -n -H -u myproduct bash -c 'cd "$1" && exec python3 deploy.py install' bash "$product"
    trust=$(sudo -n fapolicyd-cli --dump-db)
    if grep -Fq " $old_release/deploy.py " <<< "$trust"; then
        echo 'FAIL: old release still trusted'; exit 1
    fi
    grep -F " $product/deploy.py " <<< "$trust"
    echo 'PASS: old deploy.py trust removed, new deploy.py trusted'
    ;;
persistent-state)
    as_product python3 - <<'HASHES'
import hashlib, json, pathlib, ssl
root = pathlib.Path.home()
paths = [root / "config.yaml"]
for directory in ("generated-certificates", "PKI/private", "files"):
    paths.extend(p for p in (root / directory).rglob("*") if p.is_file())
assert len(paths) > 1
hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
ca = ssl.PEM_cert_to_DER_cert((root / "PKI/private/ca.crt").read_text())
print(json.dumps({"files_sha256": hashes, "ca_der_sha256": hashlib.sha256(ca).hexdigest()}, sort_keys=True))
HASHES
    ;;
unpack)
    cd "$base"
    archive="myproduct-$requested_version-offline.tar.gz"
    sha256sum -c "$archive.sha256"
    tar -xOf "$archive" "myproduct-$requested_version/VERSION" > version
    version=$(cat version)
    test "$version" = "$requested_version"
    [[ $version =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]
    cat version
    ;;
install)
    cd "$base"
    archive="myproduct-$(cat version)-offline.tar.gz"
    sha256sum -c "$archive.sha256"
    stage=$(mktemp -d /tmp/myproduct-install.XXXXXXXX)
    tar xzf "$archive" -C "$stage"
    sudo -n bash "$stage/myproduct-$(cat version)/scripts/prepare-host.sh" --port "$port"
    sudo -n -H -u myproduct mkdir -p /var/lib/myproduct/releases
    # Operatøren åpner arkivet; myproduct trenger ikke lesetilgang til operatørens hjem.
    # shellcheck disable=SC2024
    sudo -n -H -u myproduct tar xzf - -C /var/lib/myproduct/releases < "$archive"
    rm -rf -- "$stage"
    sudo -n bash -c 'cd "$1" && sha256sum -c --quiet checksums.sha256' bash "$product"
    sudo -n fapolicyd-cli --file add "$product/deploy.py" --trust-file myproduct
    sudo -n fapolicyd-cli --update
    sudo -n -H -u myproduct bash "$product/scripts/generate-certificates.sh" --root "$state" "$prod_host"
    sudo -n install -o myproduct -g myproduct -m 0600 "$product/config.example.yaml" "$state/config.yaml"
    sudo -n -H -u myproduct python3 - "$state/config.yaml" "$prod_ip" "$prod_host" "$port" <<'CONFIG'
import os, sys, yaml
with open(sys.argv[1]) as stream:
    config = yaml.safe_load(stream)
config.update(IP_ADDRESS=sys.argv[2], PUBLIC_ORIGIN="https://{}:{}".format(sys.argv[3], sys.argv[4]), HTTPS_PORT=int(sys.argv[4]))
os.chmod(sys.argv[1], 0o600)
with open(sys.argv[1], "w") as stream:
    yaml.safe_dump(config, stream)
CONFIG
    date +%s > "$base/install-start"
    sudo -n -H -u myproduct bash -c 'cd "$1" && exec python3 deploy.py install' bash "$product"
    user_service status --no-pager myproduct.service
    as_product podman images
    sudo -n -H -u myproduct cat "$product/images/images.txt" | while read -r image; do as_product podman image exists "$image"; done
    ;;
check)
    profile
    healthy
    user_service is-active myproduct-network.service
    generated=$(as_product /usr/lib/systemd/user-generators/podman-user-generator --dryrun)
    printf '%s\n' "$generated"
    grep -q 'podman-user-wait-network-online.service' <<< "$generated"
    output=$(sudo -n podman ps -aq)
    test -z "$output"
    sudo -n podman ps -a
    sudo -n ls -Zd /var/lib/myproduct /var/lib/myproduct/.local/share/containers/storage
    sudo -n python3 - <<'PY'
import pathlib, pwd, stat
account = pwd.getpwnam("myproduct")
paths = {
 "/var/lib/myproduct": 0o700,
 "/var/lib/myproduct/config.yaml": 0o600,
 "/var/lib/myproduct/generated-certificates": 0o700,
 "/var/lib/myproduct/PKI/private": 0o700,
 "/var/lib/myproduct/.config/containers/systemd/myproduct.yaml": 0o600,
 "/var/lib/myproduct/.config/containers/systemd/myproduct.kube": 0o644,
 "/var/lib/myproduct/.config/containers/systemd/myproduct.network": 0o644,
 "/var/lib/myproduct/files": 0o700,
}
paths.update({str(p): 0o600 for p in pathlib.Path("/var/lib/myproduct/files").glob("*.tar")})
for name, mode in paths.items():
    item = pathlib.Path(name).stat()
    assert item.st_uid == account.pw_uid and item.st_gid == account.pw_gid and stat.S_IMODE(item.st_mode) == mode, name
    print("PASS: myproduct:myproduct {:04o} {}".format(mode, name))
PY
    sudo -n python3 - <<'LABELS'
import os
import pathlib
import re
import stat
import subprocess
import sys

try:
    import selinux
except ImportError:
    raise SystemExit("FAIL: Python-modulen selinux mangler; installer vertens policycoreutils-python-utils før snapshot")

STORAGE = pathlib.Path("/var/lib/myproduct/.local/share/containers/storage")
CUSTOMIZABLE = pathlib.Path("/etc/selinux/targeted/contexts/customizable_types")


def context_type(context):
    """Hent typen fra en SELinux-context og avvis ugyldig format."""
    parts = context.rstrip("\x00").split(":")
    if len(parts) < 4:
        raise RuntimeError("Ugyldig SELinux-context: " + context)
    return parts[2]


def policy_type(path):
    """Hent policytypen med stiens lstat-filtype; avvis feil uten reserveoppslag."""
    try:
        mode = stat.S_IFMT(os.lstat(str(path)).st_mode)
    except OSError as error:
        raise RuntimeError("lstat feilet for {}: {}".format(path, error)) from None
    status, context = selinux.matchpathcon(str(path), mode)
    if status != 0:
        raise RuntimeError("matchpathcon feilet: " + str(path))
    return context_type(context)


def check_equivalence():
    """Bekreft container-ekvivalensen med policy-prober uten filkrav."""
    probes = ((STORAGE / "overlay-layers", "container_ro_file_t"),
              (STORAGE / "volumes/x/_data/y", "container_file_t"))
    for path, expected in probes:
        status, context = selinux.matchpathcon(str(path), 0)
        if status != 0:
            raise RuntimeError("matchpathcon feilet for policy-probe: " + str(path))
        actual = context_type(context)
        print("POLICY {} type={} expected={}".format(path, actual, expected))
        if actual != expected:
            raise RuntimeError("Container-ekvivalensen mangler eller gir feil type: " + str(path))


def check_label(path):
    """Logg faktisk og forventet type og avvis avvik fra policyen."""
    actual = context_type(os.getxattr(str(path), "security.selinux", follow_symlinks=False).decode())
    expected = policy_type(path)
    print("LABEL {} actual={} expected={}".format(path, actual, expected))
    if actual != expected:
        raise RuntimeError("SELinux-type avviker fra policyen: " + str(path))


def classify_line(line, customizable):
    """Klassifiser én dry-run-linje med smale regler eller avvis den."""
    proposal = re.fullmatch(r"Would relabel (.+) from (\S+) to (\S+)", line)
    preserved = re.fullmatch(r"(.+) not reset as customized by admin to (\S+)", line)
    if proposal:
        path, before, after = proposal.groups()
        before, after = context_type(before), context_type(after)
    elif preserved:
        path, context = preserved.groups()
        before, after = context_type(context), policy_type(path)
    else:
        raise RuntimeError("Uklassifisert restorecon-linje: " + line)
    prefix = str(STORAGE) + "/"
    if not path.startswith(prefix) or ".." in pathlib.Path(path).parts:
        raise RuntimeError("restorecon-linje utenfor lageret: " + line)
    relative = path[len(prefix):]
    # R1: container.if named transition for 'artifacts'; container.fc path default.
    if (proposal and re.fullmatch(r"overlay-containers/[0-9a-f]{64}/userdata/artifacts", relative)
            and before == "container_ro_file_t" and after == "container_var_lib_t"
            and policy_type(path) == after):
        return "ARTIFACT_DIRECTORY_TRANSITION"
    # R2/R3: container_file_t is customizable; preserve Podman's writable labels.
    if preserved and before == "container_file_t" and before in customizable:
        if re.fullmatch(r"volumes/[^/]+/_data(?:/.*)?", relative) and after == "container_file_t":
            return "CUSTOM_VOLUME_CONTENT"
        if re.fullmatch(r"overlay/[0-9a-f]{64}/diff(?:/.*)?", relative) and after == "container_ro_file_t":
            return "CUSTOM_WRITABLE_LAYER"
        if re.fullmatch(r"overlay-containers/[0-9a-f]{64}/rootfs/upper(?:/.*)?", relative) and after == "container_var_lib_t":
            return "CUSTOM_WRITABLE_ROOTFS"
    raise RuntimeError("Uklassifisert restorecon-linje: " + line)


def dryrun(arguments):
    """Logg lesende restorecon-output og avvis kommandoens feilstatus."""
    result = subprocess.run(["restorecon", "-n", "-v", "-R"] + arguments,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True, check=False)
    print("$ restorecon -n -v -R " + " ".join(arguments))
    print(result.stdout, end="")
    print(result.stderr or "", end="", file=sys.stderr)
    if result.returncode:
        raise RuntimeError("restorecon dry-run feilet: exit " + str(result.returncode))
    return result.stdout


def main():
    """Kontroller policy, faktiske labels og klassifisert dry-run uten relabeling."""
    check_equivalence()
    for name in ("", "overlay", "overlay-layers", "overlay-images", "overlay-containers", "volumes"):
        check_label(STORAGE / name)
    volumes = sorted((STORAGE / "volumes").glob("*/_data"))
    if not volumes:
        raise RuntimeError("Ingen volumdata funnet")
    for root in volumes:
        check_label(root)
        for directory, dirs, files in os.walk(str(root)):
            for name in sorted(dirs + files):
                check_label(pathlib.Path(directory) / name)
    outside = dryrun(["-e", str(STORAGE), "/var/lib/myproduct"])
    inside = dryrun([str(STORAGE)])  # Always log storage output, even if C fails.
    if outside:
        raise RuntimeError("restorecon foreslår endringer utenfor lageret")
    customizable = set(CUSTOMIZABLE.read_text().splitlines())
    for line in inside.splitlines():
        rule = classify_line(line, customizable)
        print("RULE {}: {}".format(rule, line))
    print("PASS: policy, faktiske labels og klassifisert restorecon dry-run")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        raise SystemExit("FAIL: " + str(error))
LABELS
    start_date=$(LC_ALL=C date -d "@$run_started" +%x)
    start_time=$(date -d "@$run_started" +%H:%M:%S)
    audit_events check
    as_product podman exec myproduct-todo-backend python -c 'import socket; socket.create_connection(("myproduct-todo-postgres",5432),5).close()'
    as_product podman exec myproduct-proxy-nginx wget -qO- http://myproduct-identity:8080/identity/.well-known/openid-configuration
    # Only matching pull evidence, not arbitrary application logs with auth data.
    uid=$(id -u myproduct)
    installed=$(cat "$base/install-start")
    journal=$(sudo -n journalctl _SYSTEMD_USER_UNIT=myproduct.service _UID="$uid" --since "@$installed" --no-pager)
    if grep -Ei 'Trying to pull|Pulling image|pull access denied' <<< "$journal"; then
        echo 'FAIL: install attempted a pull'; exit 1
    fi
    echo 'PASS: journal contains no pull attempts'
    ;;
prod-e2e|markers-create|markers-check)
    cd "$src"
    export PUBLIC_ORIGIN="https://$prod_host:$port" CONNECT_IP="$prod_ip"
    export SMOKE_CA_FILE="$private/ca.crt" SMOKE_PASSWORD_DIR="$private"
    if [[ $action == prod-e2e ]]; then
        .venv-smoke/bin/python dev/smoke-test.py
    else
        .venv-smoke/bin/python acceptance/markers.py "${action#markers-}" "$base/markers.json" "$run"
    fi
    ;;
stop)
    user_service stop myproduct.service
    if user_service is-active --quiet myproduct.service; then exit 1; fi
    as_product podman ps --all --pod
    output=$(as_product podman ps -q)
    test -z "$output"
    as_product podman secret ls
    as_product podman volume ls
    ;;
start|restart)
    user_service "$action" myproduct.service
    healthy
    ;;
kill)
    as_product podman kill myproduct-todo-backend
    for _ in {1..30}; do
        running=$(as_product podman inspect --format '{{.State.Running}}' myproduct-todo-backend)
        if [[ $running == true ]]; then
            healthy; exit 0
        fi
        sleep 2
    done
    as_product podman inspect --format '{{.State.Status}} restart_count={{.RestartCount}} policy={{.HostConfig.RestartPolicy.Name}}' myproduct-todo-backend
    echo 'FAIL: container did not return after podman kill within 60s'
    exit 1
    ;;
reboot)
    cat /proc/sys/kernel/random/boot_id
    sudo -n systemd-run --on-active=3 /usr/bin/systemctl reboot
    ;;
boot) cat /proc/sys/kernel/random/boot_id;;
audit)
    # Use VM local time for ausearch, derived from the recorded controller epoch.
    start_date=$(LC_ALL=C date -d "@$run_started" +%x)
    start_time=$(date -d "@$run_started" +%H:%M:%S)
    printf 'FANOTIFY/AVC evidence since %s %s (VM local time)\n' "$start_date" "$start_time"
    sudo -n systemctl is-active auditd
    audit_events collect
    ;;
cleanup) rm -rf -- "$private"; test ! -e "$private";;
*) echo "Unknown action: $action" >&2; exit 2;;
esac
