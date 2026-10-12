#!/usr/bin/env bash
# Fixed guest steps. No xtrace: commands that consume secrets must never echo them.
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
as_product() {
    sudo -n -H -u myproduct bash -c '
        cd "$HOME" || exit
        export XDG_RUNTIME_DIR="/run/user/$(id -u)"
        exec "$@"
    ' bash "$@"
}
user_service() { sudo -n systemctl --user -M myproduct@ "$@"; }
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
    if timeout 20 sudo -n podman pull docker.io/library/busybox 2>&1 | sed 's/^/pull-probe: /'; then
        echo 'FAIL: public image pulled'; exit 1
    else
        status=$?
        test "$status" = 125 -o "$status" = 124
        echo "PASS: public pull failed (exit $status)"
    fi
}
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
        test -z "$($prefix podman ps -aq)"
        test -z "$($prefix podman pod ps -q)"
        test -z "$($prefix podman volume ls -q)"
        test -z "$($prefix podman secret ls -q)"
        $prefix podman images --format '{{.Repository}}:{{.Tag}}'
    done
    test -z "$(sudo -n find /etc/containers/systemd -maxdepth 1 -name 'myproduct.*' -print)"
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
    test -z "$(git status --porcelain)"
    git rev-parse HEAD
    cat VERSION
    ;;
unit) cd "$src"; python3 -m unittest discover -s tests;;
build-images) cd "$src"; ./scripts/build-images.sh;;
dev-up)
    cd "$src"
    ./scripts/generate-certificates.sh
    cp config.example.yaml config.yaml
    chmod 600 config.yaml
    ./scripts/dev.sh up
    ;;
venv)
    cd "$src"
    python3 -m venv .venv-smoke
    .venv-smoke/bin/pip install -r apps/todo-backend/requirements.txt
    ;;
dev-e2e) cd "$src"; .venv-smoke/bin/python scripts/smoke-test.py;;
examples-setup)
    podman pull docker.io/library/busybox:1.37.0
    podman tag docker.io/library/busybox:1.37.0 localhost/offline-example:1
    ;;
example-*) cd "$src"; ./examples/run.sh "${action#example-}";;
dev-down) cd "$src"; ./scripts/dev.sh down;;
bundle)
    cd "$src"
    test -z "$(git status --porcelain)"
    ./build-bundle.sh
    cd dist
    sha256sum -c ./*.sha256
    cd ..
    cat build/bundle/myproduct-*/images/images.txt
    ;;
upgrade-bundle)
    cd "$src"
    test -z "$(git status --porcelain)"
    [[ $requested_version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
    printf '%s\n' "$requested_version" > VERSION
    test "$(git diff --name-only)" = VERSION
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
for directory in ("generated-certificates", "PKI/private"):
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
    # Final unpack/checksums run under the product identities in step 06/10.
    tar -xOf "$archive" "myproduct-$requested_version/VERSION" > version
    test "$(cat version)" = "$requested_version"
    [[ $(cat version) =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]
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
    generated=$(as_product /usr/lib/systemd/user-generators/podman-user-generator --dryrun 2>&1)
    printf '%s\n' "$generated"
    grep -q 'podman-user-wait-network-online.service' <<< "$generated"
    test -z "$(sudo -n podman ps -aq)"
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
    # Lesende SELinux-kontroll; aldri relabel under en akseptansekjøring.
    sudo -n python3 - <<'LABELS'
import os, pathlib
storage = pathlib.Path("/var/lib/myproduct/.local/share/containers/storage")
overlays = sorted(storage.glob("overlay*"))
volumes = sorted((storage / "volumes").glob("*/_data"))
assert overlays and volumes, "Missing overlay or volume storage"
for paths, expected in ((overlays, "container_ro_file_t"), (volumes, "container_file_t")):
    count = 0
    for root in paths:
        items = [root]
        if expected == "container_file_t":
            for directory, dirs, files in os.walk(str(root)):
                items.extend(pathlib.Path(directory) / name for name in dirs + files)
        for path in items:
            label = os.getxattr(str(path), "security.selinux", follow_symlinks=False).decode().strip("\x00")
            assert label.split(":")[2] == expected, "{}: {} (expected {})".format(path, label, expected)
            count += 1
    print("PASS: {} paths labeled {}".format(count, expected))
LABELS
    proposed=$(sudo -n restorecon -n -v -R /var/lib/myproduct 2>&1)
    printf '%s\n' "$proposed"
    test -z "$proposed"
    start_date=$(LC_ALL=C date -d "@$run_started" +%x)
    start_time=$(date -d "@$run_started" +%H:%M:%S)
    if avcs=$(sudo -n env LC_ALL=C ausearch --input-logs -m AVC,USER_AVC -ts "$start_date" "$start_time" -i </dev/null 2>&1); then
        printf '%s\n' "$avcs"
        echo 'FAIL: AVC events recorded since run start'; exit 1
    else
        status=$?
        printf '%s\n' "$avcs"
        test "$status" = 1 && test "$avcs" = '<no matches>'
    fi
    echo 'PASS: labels match policy; no relabel proposed; no AVC events'
    as_product podman exec myproduct-todo-backend python -c 'import socket; socket.create_connection(("myproduct-todo-postgres",5432),5).close()'
    as_product podman exec myproduct-proxy-nginx wget -qO- http://myproduct-identity:8080/identity/.well-known/openid-configuration
    # Only matching pull evidence, not arbitrary application logs with auth data.
    if sudo -n journalctl _SYSTEMD_USER_UNIT=myproduct.service _UID="$(id -u myproduct)" --since "@$(cat "$base/install-start")" --no-pager | grep -Ei 'Trying to pull|Pulling image|pull access denied'; then
        echo 'FAIL: install attempted a pull'; exit 1
    fi
    echo 'PASS: journal contains no pull attempts'
    ;;
prod-e2e|markers-create|markers-check)
    cd "$src"
    export PUBLIC_ORIGIN="https://$prod_host:$port" CONNECT_IP="$prod_ip"
    export SMOKE_CA_FILE="$private/ca.crt" SMOKE_PASSWORD_DIR="$private"
    if [[ $action == prod-e2e ]]; then
        .venv-smoke/bin/python scripts/smoke-test.py
    else
        .venv-smoke/bin/python acceptance/markers.py "${action#markers-}" "$base/markers.json" "$run"
    fi
    ;;
stop)
    user_service stop myproduct.service
    if user_service is-active --quiet myproduct.service; then exit 1; fi
    as_product podman ps --all --pod
    test -z "$(as_product podman ps -q)"
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
        if [[ $(as_product podman inspect --format '{{.State.Running}}' myproduct-todo-backend) == true ]]; then
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
    if events=$(sudo -n env LC_ALL=C ausearch -m FANOTIFY,AVC,USER_AVC --input-logs -ts "$start_date" "$start_time" -i </dev/null 2>&1); then
        printf '%s\n' "$events"
    else
        status=$?
        printf '%s\n' "$events"
        if [[ $status != 1 || $events != '<no matches>' ]]; then
            exit "$status"
        fi
        echo 'PASS: no FANOTIFY/AVC events in this run interval'
    fi
    ;;
cleanup) rm -rf -- "$private"; test ! -e "$private";;
*) echo "Unknown action: $action" >&2; exit 2;;
esac
