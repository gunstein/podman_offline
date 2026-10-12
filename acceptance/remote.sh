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
base="$HOME/podman-offline-acceptance/$run"
src="$base/src"
product="$base/product"
private="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/podman-offline-$run"
facts() {
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
    sudo -n systemctl is-active myproduct.service
    sudo -n podman ps --all --pod
    sudo -n podman ps -a --format json | python3 -c '
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
    sudo -n firewall-cmd --permanent --add-rich-rule="rule family=ipv4 source address=$lab port port=$port protocol=tcp accept"
    sudo -n firewall-cmd --add-rich-rule="rule family=ipv4 source address=$lab port port=$port protocol=tcp accept"
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
unpack)
    cd "$base"
    sha256sum -c ./*.sha256
    mkdir product
    tar -xzf ./*.tar.gz --strip-components=1 -C product
    cd product
    sha256sum -c --quiet checksums.sha256
    cat VERSION
    ;;
install)
    cd "$product"
    ./scripts/generate-certificates.sh "$prod_host"
    python3 - "$prod_ip" "$prod_host" "$port" <<'PY'
import os, sys, yaml
with open("config.example.yaml") as stream:
    config = yaml.safe_load(stream)
config.update(IP_ADDRESS=sys.argv[1], PUBLIC_ORIGIN="https://{}:{}".format(sys.argv[2], sys.argv[3]), HTTPS_PORT=int(sys.argv[3]))
with open(os.open("config.yaml", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
    yaml.safe_dump(config, stream)
PY
    # Network is installed by the product's .network Quadlet in this revision.
    date +%s > "$base/install-start"
    sudo -n ./deploy install
    sudo -n podman images
    while read -r image; do sudo -n podman image exists "$image"; done < images/images.txt
    ;;
check)
    healthy
    sudo -n systemctl is-active myproduct-network.service
    sudo -n /usr/lib/systemd/system-generators/podman-system-generator --dryrun
    sudo -n python3 - <<'PY'
import pathlib, stat
paths = {
 "/etc/containers/systemd/myproduct.yaml": 0o600,
 "/etc/containers/systemd/myproduct.kube": 0o644,
 "/etc/containers/systemd/myproduct.network": 0o644,
 "/var/lib/myproduct/files": 0o700,
}
paths.update({str(p): 0o600 for p in pathlib.Path("/var/lib/myproduct/files").glob("*.tar")})
for name, mode in paths.items():
    item = pathlib.Path(name).stat()
    assert item.st_uid == item.st_gid == 0 and stat.S_IMODE(item.st_mode) == mode, name
    print("PASS: root:root {:04o} {}".format(mode, name))
PY
    sudo -n podman exec myproduct-todo-backend python -c 'import socket; socket.create_connection(("myproduct-todo-postgres",5432),5).close()'
    sudo -n podman exec myproduct-proxy-nginx wget -qO- http://myproduct-identity:8080/identity/.well-known/openid-configuration
    # Only matching pull evidence, not arbitrary application logs with auth data.
    if sudo -n journalctl -u myproduct.service --since "@$(cat "$base/install-start")" --no-pager | grep -Ei 'Trying to pull|Pulling image|pull access denied'; then
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
    sudo -n systemctl stop myproduct.service
    if sudo -n systemctl is-active --quiet myproduct.service; then exit 1; fi
    sudo -n podman ps --all --pod
    test -z "$(sudo -n podman ps -q)"
    sudo -n podman secret ls
    sudo -n podman volume ls
    ;;
start|restart)
    sudo -n systemctl "$action" myproduct.service
    healthy
    ;;
kill)
    sudo -n podman kill myproduct-todo-backend
    for attempt in {1..30}; do
        if [[ $(sudo -n podman inspect --format '{{.State.Running}}' myproduct-todo-backend) == true ]]; then
            healthy; exit 0
        fi
        sleep 2
    done
    sudo -n podman inspect --format '{{.State.Status}} restart_count={{.RestartCount}} policy={{.HostConfig.RestartPolicy.Name}}' myproduct-todo-backend
    echo 'FAIL: container did not return after podman kill within 60s'
    exit 1
    ;;
reboot)
    cat /proc/sys/kernel/random/boot_id
    sudo -n systemd-run --on-active=3 /usr/bin/systemctl reboot
    ;;
boot) cat /proc/sys/kernel/random/boot_id;;
cleanup) rm -rf -- "$private"; test ! -e "$private";;
*) echo "Unknown action: $action" >&2; exit 2;;
esac
