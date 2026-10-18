#!/usr/bin/env bash
# Run fixed acceptance steps on the VMs without logging secrets.
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
old_version=${11:-}
bundle=${12:-app1}
# product: in the bundles.yaml under test; also the service user (prepare-host default).
product_name=${13:-myproduct}
# Any component ID; the bundle's own descriptor decides what it may do.
[[ $bundle =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] || exit 2
[[ $product_name =~ ^[a-z]([a-z0-9-]{0,30}[a-z0-9])?$ ]] || exit 2
# Python steps read the name from the environment; sudo passes it with env.
export PRODUCT_NAME=$product_name
state=/var/lib/$product_name
base="$HOME/podman-offline-acceptance/$run"
src="$base/src"
# The renamed product generated from $src by acceptance/renamed_product.py.
renamed="$base/renamed"
version=$requested_version
if [[ -z $version && -f $base/version-$bundle ]]; then version=$(cat "$base/version-$bundle"); fi
product="$state/releases/$product_name-$bundle-${version:-RELEASE}"
private="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/podman-offline-$run"
# Run commands as the service user from its home with the right runtime.
as_product() {
    sudo -n -H -u "$product_name" env PRODUCT_NAME="$product_name" bash -c '
        cd "$HOME" || exit
        export XDG_RUNTIME_DIR="/run/user/$(id -u)"
        exec "$@"
    ' bash "$@"
}
# Control the product service in the service user's systemd instance.
user_service() { sudo -n systemctl --user -M "$product_name@" "$@"; }
# List only validated installed component markers, never their private state.
installed_components() {
    as_product python3 - <<'INSTALLED'
import pathlib
import re


def main():
    """Return installed component names after strict name, version and metadata validation."""
    names = []
    home = pathlib.Path.home()
    for path in sorted((home / "installed").glob("*")):
        if (
            not re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?", path.name)
            or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", path.read_text().strip())
            or not (home / "metadata" / (path.name + ".json")).is_file()
        ):
            raise SystemExit("FAIL: invalid installed component marker")
        names.append(path.name)
    if not names:
        raise SystemExit("FAIL: no installed component")
    print("\n".join(names))


main()
INSTALLED
}
# Verify and trust only this bundle's release, reusing an already prepared release.
prepare_release() {
    local trust_status=0 trust_output
    cd "$base"
    archive="$product_name-$bundle-$version-offline.tar.gz"
    sha256sum -c "$archive.sha256"
    if ! sudo -n test -d "$product"; then
        # shellcheck disable=SC2024
        as_product tar xzf - -C "$state/releases" < "$archive"
    fi
    sudo -n bash -c 'cd "$1" && sha256sum -c --quiet checksums.sha256' bash "$product"
    # Retry trust even after a previous attempt extracted the release successfully.
    trust_output=$(sudo -n fapolicyd-cli --file add "$product/deployment/" --trust-file "$product_name-$bundle" 2>&1) || trust_status=$?
    # fapolicyd 1.4.5 returns 9 for an entirely duplicate add. Accept only that
    # diagnostic, then still require every package file in the live database.
    if [[ $trust_status != 0 ]]; then
        if [[ $trust_status != 9 || $trust_output != *"After removing duplicates, there is nothing to add"* ]]; then
            printf '%s\n' "$trust_output" >&2
            return "$trust_status"
        fi
        echo 'Release package already listed; verifying live trust'
    elif [[ -n $trust_output ]]; then
        printf '%s\n' "$trust_output"
    fi
    sudo -n fapolicyd-cli --update
    wait_trust "$product/deployment/"
}
# ./deploy validate must pass for this release before it is installed (backlog 23).
validate_release() {
    local output
    output=$(sudo -n -H -u "$product_name" bash -c 'cd "$1" && exec bash ./deploy validate' bash "$product")
    printf '%s\n' "$output"
    [[ $output == *"[OK] validated $bundle;"* ]] || { echo "FAIL: validate did not pass for $bundle" >&2; return 1; }
}
# Create only missing component configs and credentials; upgrades reuse them.
install_configuration() {
    local component components existing
    components=$bundle
    for component in $components; do
        existing=0
        if sudo -n test -e "$state/$component/config.yaml"; then existing=1; fi
        as_product bash "$product/deploy" init-config "$component"
        # The component that accepts routes is the gateway; edit its new config first.
        if [[ $existing == 0 ]] && as_product python3 -c 'import sys, yaml; sys.exit("routes" not in yaml.safe_load(open(sys.argv[1]))["accepts"])' "$product/bundle.yaml"; then
        as_product python3 - "$state/$component/config.yaml" "$prod_ip" "$prod_host" "$port" <<'CONFIG'
import pathlib
import sys
import yaml


def main():
    """Edit the newly initialized gateway explicitly before initializing dependents."""
    path = pathlib.Path(sys.argv[1])
    with path.open() as stream:
        config = yaml.safe_load(stream)
    config.update(IP_ADDRESS=sys.argv[2], PUBLIC_ORIGIN="https://{}:{}".format(sys.argv[3], sys.argv[4]), HTTPS_PORT=int(sys.argv[4]))
    with path.open("w") as stream:
        yaml.safe_dump(config, stream)
    print("PASS: initial gateway settings edited: " + str(path))


main()
CONFIG
        fi
        demo_credentials "$component"
    done
}
# Demo provisioning on the target. The renamed product reuses the demo script
# under the demo name, then moves the result; mirrors renamed_product.NAMES.
demo_credentials() {
    local component=$1 demo
    case "$component" in
        gateway) demo=platform;;
        login-service) demo=identity;;
        orders) demo=app1;;
        inventory) demo=app2;;
        manual) demo=help;;
        *) demo=$component;;
    esac
    if [[ $demo == "$component" ]]; then
        as_product bash "$product/scripts/generate-certificates.sh" --root "$state" "$component" "$prod_host"
        return
    fi
    if sudo -n test -e "$state/$demo/credentials"; then
        echo "FAIL: unexpected demo credential directory for $component" >&2; return 1
    fi
    # Move existing credentials back so the script preserves them byte-for-byte.
    if sudo -n test -e "$state/$component/credentials"; then
        as_product mkdir -m 700 -p "$state/$demo"
        as_product mv "$state/$component/credentials" "$state/$demo/credentials"
    fi
    as_product bash "$product/scripts/generate-certificates.sh" --root "$state" "$demo" "$prod_host"
    as_product mkdir -m 700 -p "$state/$component"
    as_product mv "$state/$demo/credentials" "$state/$component/credentials"
    as_product rmdir "$state/$demo"
}
# Collect audit with separate streams and accept only the documented empty result.
audit_events() {
    sudo -n python3 - "$start_date" "$start_time" "$1" <<'AUDIT'
import os
import subprocess
import sys


def collect():
    """Log the audit streams and reject errors or denials in check mode."""
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
# Preserve safe launcher evidence before reboot discards the volatile journal.
health_launch_diagnostics() {
    sudo -n env PRODUCT_NAME="$product_name" python3 - "$run_started" <<'LAUNCH_DIAGNOSTICS'
import json
import os
import pathlib
import pwd
import re
import subprocess
import sys

UNIT = re.compile(r"\b[0-9a-f]{64}(?:-[0-9a-f]+)?(?:-startup)?\.service\b")
PROPERTIES = ("LoadState", "ActiveState", "SubState", "Result", "MainPID",
              "ExecMainPID", "ExecMainCode", "ExecMainStatus", "ExecStart")
EXEC_ERROR = re.compile(
    r"Failed (?:at step [A-Z_]+ spawning|to execute) /usr/bin/podman: "
    r"(?:Operation not permitted|Permission denied|No such file or directory)")
EXIT_ERROR = re.compile(r"Main process exited, code=exited, status=\d+/[A-Z_]+")
RESULT_ERROR = re.compile(r"Failed with result '(?:exit-code|signal|core-dump|timeout|resources|protocol)'")


def command(arguments):
    """Read separate streams without printing unfiltered journal or unit data."""
    result = subprocess.run(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True, check=False, timeout=30)
    print(result.stderr or "", end="", file=sys.stderr)
    if result.returncode:
        raise RuntimeError("Launch diagnostics command failed: " + arguments[0]
                           + " exit " + str(result.returncode))
    return result.stdout


def journal_events(output):
    """Keep only recognized systemd failures and safe identifiers from journal JSON."""
    events, units = [], set()
    for line in output.splitlines():
        try:
            row = json.loads(line)
            if not isinstance(row, dict) or not isinstance(row.get("MESSAGE"), str):
                raise ValueError("Invalid journal fields")
        except (TypeError, ValueError):
            raise RuntimeError("Invalid journal JSON in launch diagnostics") from None
        names = set()
        for key in ("USER_UNIT", "UNIT", "_SYSTEMD_USER_UNIT", "OBJECT_SYSTEMD_USER_UNIT", "MESSAGE"):
            if isinstance(row.get(key), str):
                names.update(UNIT.findall(row[key]))
        units.update(names)
        errors = [match.group(0) for pattern in (EXEC_ERROR, EXIT_ERROR, RESULT_ERROR)
                  for match in [pattern.search(row["MESSAGE"])] if match]
        if not errors:
            continue
        event = {"units": sorted(names), "errors": errors}
        for key in ("__REALTIME_TIMESTAMP", "_PID", "OBJECT_PID"):
            value = row.get(key)
            if isinstance(value, str) and value.isdigit():
                event[key] = value
        for key, allowed in (("_EXE", ("/usr/lib/systemd/systemd", "/usr/bin/podman")),
                             ("_COMM", ("systemd", "(podman)", "podman"))):
            if row.get(key) in allowed:
                event[key] = row[key]
        events.append(event)
    return events, units


def unit_state(name, output):
    """Project loaded launcher state or mark removed transient units unavailable."""
    values = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key not in PROPERTIES or key in values:
            raise RuntimeError("Invalid systemd properties in launch diagnostics")
        values[key] = value
    missing = set(PROPERTIES) - set(values)
    if missing and not (values.get("LoadState") == "not-found" and missing == {"ExecStart"}):
        raise RuntimeError("Missing systemd properties in launch diagnostics")
    result = {"unit": name}
    for key, value in values.items():
        if key == "ExecStart":
            match = re.search(r"path=/usr/bin/podman ; argv\[\]=/usr/bin/podman healthcheck run ([0-9a-f]{64}) ;", value)
            result[key] = ("/usr/bin/podman healthcheck run " + match.group(1)
                           if match else "withheld: not the expected healthcheck command")
        elif re.fullmatch(r"[A-Za-z0-9_-]*", value):
            result[key] = value
        else:
            raise RuntimeError("Invalid systemd state value in launch diagnostics")
    if result["LoadState"] == "not-found":
        return {"unit": name, "LoadState": "not-found",
                "evidence": "unavailable: transient unit removed"}
    return result


def main():
    """Collect read-only launcher state and failures without application messages or environments."""
    try:
        user = pwd.getpwnam(os.environ["PRODUCT_NAME"])
    except KeyError:
        print("LAUNCH_DIAGNOSTICS: service user absent; no product launcher to inspect")
        return
    print("LAUNCH_DIAGNOSTICS boot_id=" + pathlib.Path("/proc/sys/kernel/random/boot_id").read_text().strip())
    print(command(["journalctl", "--list-boots", "--no-pager"]), end="")
    output = command(["journalctl", "--since", "@" + sys.argv[1],
                      "_UID=" + str(user.pw_uid), "--output=json", "--no-pager"])
    events, units = journal_events(output)
    print("LAUNCH_JOURNAL records=" + str(len(output.splitlines())))
    for event in events:
        print("LAUNCH_EVENT " + json.dumps(event, sort_keys=True))
    print("LAUNCH_EVENTS count=" + str(len(events)))
    listing = command(["systemctl", "--user", "-M", os.environ["PRODUCT_NAME"] + "@", "list-units",
                       "--all", "--type=service", "--plain", "--no-legend", "--no-pager"])
    units.update(UNIT.findall(listing))
    print("LAUNCH_UNITS count=" + str(len(units)))
    for name in sorted(units):
        output = command(["systemctl", "--user", "-M", os.environ["PRODUCT_NAME"] + "@", "show", name]
                         + ["--property=" + key for key in PROPERTIES])
        print("LAUNCH_UNIT " + json.dumps(unit_state(name, output), sort_keys=True))
    print("PASS: read-only launcher diagnostics collected; unrecognized messages and arguments withheld")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        raise SystemExit("FAIL: " + str(error))
LAUNCH_DIAGNOSTICS
}
# Wait, read-only, for exact trust paths after the daemon's asynchronous update.
wait_trust() {
    local wanted=${1%/}/ removed=${2:-} expected dump status attempt
    if [[ -n $removed ]]; then removed=${removed%/}/; fi
    expected=$(sudo -n find "$wanted" -type f -print) || {
        echo 'FAIL: could not enumerate package trust files' >&2; return 1;
    }
    [[ -n $expected ]] || { echo 'FAIL: empty deployment package' >&2; return 1; }
    for attempt in {1..30}; do
        dump=$(timeout 10 sudo -n fapolicyd-cli --dump-db) || {
            echo 'FAIL: could not read trust database' >&2; return 1;
        }
        status=0
        awk -v expected="$expected" -v wanted="$wanted" -v removed="$removed" '
            BEGIN {
                count=split(expected, files, "\n")
                for (i=1; i<=count; i++) required[files[i]]=1
            }
            {
                path=$0
                sub(/^[^[:space:]]+[[:space:]]+/, "", path)
                sub(/[[:space:]]+[0-9]+[[:space:]]+[[:xdigit:]]+[[:space:]]*$/, "", path)
                if (NF < 4 || path !~ /^\// || $(NF-1) !~ /^[0-9]+$/ ||
                    length($NF) != 64 || $NF !~ /^[[:xdigit:]]+$/) invalid=1
                if (index(path, wanted) == 1) {
                    if (!(path in required) || ++seen[path] != 1) invalid=1
                }
                if (removed != "" && index(path, removed) == 1) old=1
            }
            END {
                if (NR == 0 || invalid) exit 2
                for (path in required) if (seen[path] != 1) exit 1
                if (old) exit 1
            }
        ' <<< "$dump" || status=$?
        case "$status" in
            0) printf 'PASS: package trust ready for %s; removed=%s\n' "$wanted" "${removed:-none}"; return;;
            1) printf 'WAIT: package trust update pending for %s; removed=%s (%s/30)\n' "$wanted" "${removed:-none}" "$attempt";;
            *) echo 'FAIL: invalid or empty trust database output' >&2; return 1;;
        esac
        if [[ $attempt != 30 ]]; then sleep 1; fi
    done
    echo 'FAIL: trust update did not finish within 30 checks' >&2
    return 1
}

# Validate the VM role's fapolicyd, SELinux and firewalld profile.
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
# Log OS, tool and boot data after the profile check.
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
# Wait for automatic start after reboot without starting or restarting the service.
wait_boot_service() {
    local component components
    components=$(installed_components)
    for component in $components; do
    for _ in {1..120}; do
        status=0
        service=$(user_service is-active "$product_name-$component.service") || status=$?
        printf 'boot-service state=%s exit=%s\n' "$service" "$status"
        case "$service:$status" in
            active:0) break;;
            failed:*)
                user_service status --no-pager "$product_name-$component.service" || true
                echo 'FAIL: product service failed after reboot'; return 1;;
            activating:3|inactive:3) sleep 2;;
            *) echo 'FAIL: unexpected service state or command failure'; return 1;;
        esac
    done
    if [[ $service != active || $status != 0 ]]; then
        user_service status --no-pager "$product_name-$component.service" || true
        echo 'FAIL: product service did not become active within 240s'; return 1
    fi
    done
}
# Confirm blocked internet without accepting missing tools as network evidence.
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
    status=0
    # FD 3 keeps stdout; only stderr is captured to validate the network error.
    { probe_error=$(timeout 20 sudo -n podman pull docker.io/library/busybox 2>&1 1>&3) || status=$?; } 3>&1
    printf '%s\n' "$probe_error" | sed 's/^/pull-probe: /' >&2
    case "$status" in
        124) ;;
        125)
            if ! grep -Eqi 'lookup|dial tcp|i/o timeout|connection refused|network is unreachable|no such host' <<< "$probe_error"; then
                echo 'FAIL: pull failed for a reason other than network isolation'; exit 1
            fi;;
        0) echo 'FAIL: public image pulled'; exit 1;;
        *) echo "FAIL: unexpected pull exit $status"; exit 1;;
    esac
    echo "PASS: public pull failed (exit $status)"
}
# Wait for all manifest-defined app containers and their Podman health status.
healthy() {
    local component components
    components=$(installed_components)
    for component in $components; do user_service is-active "$product_name-$component.service"; done
    as_product python3 - <<'HEALTHY'
import json
import os
import pathlib
import subprocess
import sys
import time
import yaml


def podman(arguments):
    """Read Podman stdout without private inspect content, and log stderr on every outcome."""
    result = subprocess.run(["podman"] + arguments, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, universal_newlines=True,
                            check=False, timeout=10)
    print(result.stderr or "", end="", file=sys.stderr)
    if result.returncode:
        raise RuntimeError("Podman check failed: exit " + str(result.returncode))
    return result.stdout


def expected_containers(path):
    """Read unique app and init-container names from the installed Pod YAML."""
    expected, init = set(), set()
    with path.open() as stream:
        for doc in yaml.safe_load_all(stream):
            if not isinstance(doc, dict) or doc.get("kind") != "Pod":
                continue
            pod = doc["metadata"]["name"]
            for group, target in (("containers", expected), ("initContainers", init)):
                for container in doc["spec"].get(group, []):
                    name = pod + "-" + container["name"]
                    if name in expected or name in init:
                        raise RuntimeError("Duplicate expected container name: " + name)
                    target.add(name)
    if not expected:
        raise RuntimeError("No app containers in the installed YAML")
    return expected, init


def states(expected, init):
    """Require the exact container inventory and return only public health fields."""
    ids = podman(["ps", "-aq"]).splitlines()
    if not ids or any(not value.strip() for value in ids):
        raise RuntimeError("Missing container inventory")
    rows = json.loads(podman(["inspect", "--format", "json"] + ids))
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("Invalid inspect list")
    found = {}
    for row in rows:
        if type(row["IsInfra"]) is not bool or type(row["IsService"]) is not bool:
            raise RuntimeError("Invalid inventory flags")
        if row["IsInfra"] or row["IsService"]:
            continue
        name = row["Name"]
        if name in init:
            continue
        if name not in expected or name in found:
            raise RuntimeError("Unknown or duplicate container: " + str(name))
        state = row["State"]
        running, health = state["Status"], state["Health"]["Status"]
        if not isinstance(running, str) or health not in ("starting", "healthy", "unhealthy"):
            raise RuntimeError("Invalid health status: " + name)
        found[name] = (running, health)
    if set(found) != expected:
        raise RuntimeError("Missing containers: " + ", ".join(sorted(expected - set(found))))
    return found


def main():
    """Wait up to 150 seconds for healthy; reject inventory, command and parse errors at once."""
    folder = pathlib.Path.home() / ".config/containers/systemd"
    paths = sorted(folder.glob(os.environ["PRODUCT_NAME"] + "-*.yaml"))
    if not paths:
        raise RuntimeError("No installed component YAML")
    expected, init = set(), set()
    for path in paths:
        names, initial = expected_containers(path)
        if (expected | init) & (names | initial):
            raise RuntimeError("Duplicate container names across components")
        expected.update(names)
        init.update(initial)
    deadline = time.monotonic() + 150
    while True:
        current = states(expected, init)
        for name, (running, health) in sorted(current.items()):
            print("HEALTH {} state={} health={}".format(name, running, health), flush=True)
            if running != "running" or health == "unhealthy":
                raise RuntimeError("Container is not healthy: " + name)
        if all(health == "healthy" for _, health in current.values()):
            print("PASS: all {} app containers are running and healthy".format(len(expected)))
            return
        if time.monotonic() >= deadline:
            raise RuntimeError("Health status still starting after 150s")
        time.sleep(min(2, max(0, deadline - time.monotonic())))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired) as error:
        raise SystemExit("FAIL: " + str(error))
HEALTHY
}
# Wait for the backend through the HTTPS proxy before authenticated marker checks.
wait_backend() {
    for _ in {1..30}; do
        status=0
        http=$(as_product curl --noproxy '*' --cacert "$state/PKI/private/ca.crt" \
            --resolve "$prod_host:$port:$prod_ip" --silent --show-error --max-time 5 \
            --output /dev/null --write-out '%{http_code}' "https://$prod_host:$port/app1/api/health") || status=$?
        printf 'backend-health HTTP=%s exit=%s\n' "$http" "$status"
        if [[ $status == 0 && $http == 200 ]]; then
            echo 'PASS: backend ready through HTTPS proxy'; return
        fi
        sleep 2
    done
    echo 'FAIL: backend did not become ready through HTTPS proxy'
    return 1
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
    output=$(sudo -n find /etc/containers/systemd -maxdepth 1 -name "$product_name.*" -print)
    test -z "$output"
    if [[ $role == PROD ]]; then
        if getent passwd "$product_name"; then echo "FAIL: $product_name user already exists"; exit 1; fi
        sudo -n test ! -e "$state"
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
database-runtime) cd "$src"; python3 acceptance/database_test.py;;
pull-images) cd "$src"; ./dev/pull-images.sh;;
registry-test) cd "$src"; python3 acceptance/registry_test.py "$base" "$run";;
dev-up)
    cd "$src"
    cp config/dev.yaml.example config/dev.yaml
    chmod 600 config/dev.yaml
    # The shipped demo provisions its credentials explicitly before generic dev up.
    ./dev/demo-credentials.sh
    # Every catalog component validates with its dev config before dev up (backlog 23).
    output=$(./deploy validate)
    printf '%s\n' "$output"
    [[ $output == *"[OK] validated platform, identity, app1, app2, help;"* ]]
    ./dev/dev.sh up
    ;;
venv)
    cd "$src"
    python3 -m venv .venv-smoke
    .venv-smoke/bin/pip install -r apps/todo-backend/requirements.txt
    ;;
dev-e2e)
    cd "$src"
    for app in app1 app2; do APP_BASE_PATH=/$app .venv-smoke/bin/python dev/smoke-test.py; done
    ;;
examples-setup)
    image=$(cat "$base/registry-fixture/image.txt")
    podman image exists "$image"
    podman tag "$image" localhost/offline-example:1
    echo 'PASS: examples use the BusyBox image downloaded from the TLS test registry'
    ;;
example-*) cd "$src"; ./examples/run.sh "${action#example-}";;
dev-down) cd "$src"; ./dev/dev.sh down;;
renamed-generate)
    # Only YAML, descriptors and runtime settings change; deploy code stays as checked out.
    python3 "$src/acceptance/renamed_product.py" generate "$src" "$renamed"
    for path in deployment bundle.py dev scripts quadlet deploy build-bundle.sh; do
        diff -r -x __pycache__ "$src/$path" "$renamed/$path"
    done
    echo 'PASS: generic deploy, bundle, dev and script files are identical to the source'
    ;;
renamed-dev-up)
    cd "$renamed"
    cp config/dev.yaml.example config/dev.yaml
    chmod 600 config/dev.yaml
    host=$(python3 -B - <<'RENAMED_HOST'
from urllib.parse import urlsplit
from deployment import deploy

known, settings = deploy.dev_settings()
deploy.check_dev_components(known, settings)
print(urlsplit(settings["gateway"]["PUBLIC_ORIGIN"]).hostname)
RENAMED_HOST
)
    python3 acceptance/renamed_product.py credentials build/dev "$host"
    output=$(./deploy validate)
    printf '%s\n' "$output"
    [[ $output == *"[OK] validated gateway, login-service, orders, inventory, manual;"* ]]
    ./dev/dev.sh up
    pods=$(podman pod ps --format '{{.Name}}' | sort | tr '\n' ' ')
    test "$pods" = 'gateway-proxy inventory-postgres inventory-todo login-service-postgres login-service-server manual-web orders-postgres orders-todo '
    echo "PASS: renamed dev pods $pods"
    ;;
renamed-dev-e2e)
    cd "$renamed"
    export SMOKE_PASSWORD_DIR="$renamed/build/dev/login-service/credentials/users"
    for path in /orders /stock; do APP_BASE_PATH=$path "$src/.venv-smoke/bin/python" dev/smoke-test.py; done
    ;;
renamed-dev-down)
    cd "$renamed"
    ./dev/dev.sh down
    output=$(podman pod ps -q)
    test -z "$output"
    ;;
bundle-list) cat "$src/dist/current-bundles.txt";;
renamed-bundle-list) cat "$renamed/dist/current-bundles.txt";;
renamed-bundle)
    cd "$renamed"
    ./build-bundle.sh
    while IFS= read -r name; do
        [[ $name =~ ^"$product_name"-(gateway|login-service|orders|inventory|manual)-[0-9]+\.[0-9]+\.[0-9]+-offline\.tar\.gz$ ]]
        (cd dist && sha256sum -c "$name.sha256")
    done < dist/current-bundles.txt
    test "$(wc -l < dist/current-bundles.txt)" = 5
    cat dist/current-bundles.txt
    ;;
renamed-remove-manual)
    # Documented removal: dev down first (done), then drop the catalog entry and directory.
    cd "$renamed"
    python3 - <<'REMOVE_MANUAL'
import yaml

with open("bundles.yaml") as stream:
    catalog = yaml.safe_load(stream)
del catalog["components"]["manual"]
with open("bundles.yaml", "w") as stream:
    yaml.safe_dump(catalog, stream, sort_keys=False)
REMOVE_MANUAL
    rm -r components/manual
    ./dev/dev.sh up
    pods=$(podman pod ps --format '{{.Name}}' | sort | tr '\n' ' ')
    test "$pods" = 'gateway-proxy inventory-postgres inventory-todo login-service-postgres login-service-server orders-postgres orders-todo '
    http=$(curl --noproxy '*' --cacert build/dev/PKI/private/ca.crt --resolve myproduct-proxy:8443:127.0.0.1 \
        --silent --show-error --max-time 5 --output /dev/null --write-out '%{http_code}' https://myproduct-proxy:8443/help/)
    test "$http" = 404
    # manual served the help pages, so they are expected to be gone now.
    SMOKE_HELP=0 SMOKE_PASSWORD_DIR="$renamed/build/dev/login-service/credentials/users" APP_BASE_PATH=/orders \
        "$src/.venv-smoke/bin/python" dev/smoke-test.py
    ./dev/dev.sh down
    ./build-bundle.sh
    test "$(wc -l < dist/current-bundles.txt)" = 4
    if grep -q manual dist/current-bundles.txt; then echo 'FAIL: manual still in the product' >&2; exit 1; fi
    ls dist/"$product_name"-manual-*-offline.tar.gz
    echo 'PASS: manual removed from dev and new bundles; its earlier archive is retained'
    ;;
renamed-inventory-drop)
    # A newer inventory release that no longer declares a route or a client.
    cd "$renamed"
    python3 - <<'DROP_REGISTRATIONS'
import pathlib
import yaml

with open("bundles.yaml") as stream:
    catalog = yaml.safe_load(stream)
entry = catalog["components"]["inventory"]
entry.pop("routes")
entry.pop("clients")
entry["version_file"] = "INVENTORY_VERSION"
with open("bundles.yaml", "w") as stream:
    yaml.safe_dump(catalog, stream, sort_keys=False)
major, minor, patch = pathlib.Path("VERSION").read_text().strip().split(".")
pathlib.Path("INVENTORY_VERSION").write_text(f"{major}.{minor}.{int(patch) + 1}\n")
DROP_REGISTRATIONS
    rm components/inventory/route.conf components/inventory/client.yaml
    ./build-bundle.sh inventory >&2
    name="$product_name-inventory-$(cat INVENTORY_VERSION)-offline.tar.gz"
    (cd dist && sha256sum -c "$name.sha256" >&2)
    echo "$name"
    ;;
renamed-registrations-removed)
    sudo -n test ! -e "$state/routes/inventory.conf"
    sudo -n test ! -e "$state/clients/inventory"
    sudo -n test -f "$state/routes/orders.conf"
    sudo -n test -f "$state/clients/orders/client.json"
    sudo -n test ! -e "$state/pending-operation.json"
    test "$(sudo -n cat "$state/installed/inventory")" = "$version"
    as_product podman volume exists inventory-data
    http=$(as_product curl --noproxy '*' --cacert "$state/PKI/private/ca.crt" \
        --resolve "$prod_host:$port:$prod_ip" --silent --show-error --max-time 5 \
        --output /dev/null --write-out '%{http_code}' "https://$prod_host:$port/stock/")
    test "$http" = 404
    echo "PASS: inventory $version without route and client: /stock 404, client gone, orders kept"
    ;;
renamed-init-check)
    # orders keeps the demo's schema init container; it must have finished successfully.
    status=$(as_product podman ps --all --filter name=orders-todo-prepare-database --format '{{.Status}}')
    [[ $status == Exited\ \(0\)* ]]
    as_product podman volume exists orders-data
    as_product podman volume exists inventory-data
    sudo -n test ! -e "$state/platform"
    sudo -n test ! -e "$state/app1"
    echo 'PASS: orders init container exited 0; renamed volumes exist; no demo component state'
    ;;
renamed-e2e|renamed-markers-create|renamed-markers-check|renamed-survivor)
    cd "$src"
    export PUBLIC_ORIGIN="https://$prod_host:$port" CONNECT_IP="$prod_ip"
    export SMOKE_CA_FILE="$private/ca.crt" SMOKE_PASSWORD_DIR="$private"
    paths="/orders /stock"
    if [[ $action == renamed-survivor ]]; then paths=/orders; fi
    for path in $paths; do
        export APP_BASE_PATH=$path
        if [[ $action == renamed-e2e ]]; then
            .venv-smoke/bin/python dev/smoke-test.py
        else
            operation=${action#renamed-markers-}
            if [[ $action == renamed-survivor ]]; then operation=check; fi
            .venv-smoke/bin/python acceptance/markers.py "$operation" "$base/markers-renamed${path//\//-}.json" "$run"
        fi
    done
    ;;
renamed-uninstall)
    case "$bundle" in
        inventory) path=/stock volume=inventory-data;;
        manual) path=/help volume=;;
        *) echo "Unsupported renamed uninstall: $bundle" >&2; exit 2;;
    esac
    sudo -n -H -u "$product_name" bash -c 'cd "$1" && exec bash ./deploy uninstall' bash "$product"
    sudo -n fapolicyd-cli --file delete "$product/deployment/" --trust-file "$product_name-$bundle"
    sudo -n fapolicyd-cli --update
    sudo -n test ! -e "$state/installed/$bundle"
    sudo -n test ! -e "$state/metadata/$bundle.json"
    sudo -n test ! -e "$state/routes/$bundle.conf"
    sudo -n test ! -e "$state/clients/$bundle"
    sudo -n test -f "$state/$bundle/config.yaml"
    sudo -n test -d "$state/clients/orders"
    if [[ -n $volume ]]; then as_product podman volume exists "$volume"; fi
    healthy
    http=$(as_product curl --noproxy '*' --cacert "$state/PKI/private/ca.crt" \
        --resolve "$prod_host:$port:$prod_ip" --silent --show-error --max-time 5 \
        --output /dev/null --write-out '%{http_code}' "https://$prod_host:$port$path/")
    test "$http" = 404
    echo "PASS: $bundle removed, route inactive, data retained; orders and its client remain"
    ;;
bundle)
    cd "$src"
    output=$(git status --porcelain)
    test -z "$output"
    ./build-bundle.sh
    cd dist
    sha256sum -c ./*.sha256
    cd ..
    cat build/bundle/"$product_name"-*/images/images.txt
    ;;
legacy-build)
    cd "$src"
    legacy_revision=86e8e27ed38d6e209eecf018299fd48ec2ce0b1b
    git cat-file -e "$legacy_revision^{commit}"
    git worktree add --detach "$base/legacy" "$legacy_revision"
    cd "$base/legacy"
    test "$(git rev-parse HEAD)" = "$legacy_revision"
    test "$(cat VERSION)" = 0.2.0
    test "$(cat CORE_VERSION)" = 0.2.0
    ./dev/build-images.sh
    ./dev/pull-images.sh
    ./build-bundle.sh
    (cd dist && sha256sum -c ./*.sha256)
    mkdir -p "$src/dist"
    cp dist/myproduct-*-0.2.0-offline.tar.gz* "$src/dist/"
    ;;
legacy-install)
    sudo -n fapolicyd-cli --dump-db | grep -F "$state/releases/myproduct-" | grep -v -F "/myproduct-$bundle-" | sort > "$base/legacy-trust-before"
    prepare_release
    # Actual release wrapper, called from the account home rather than release cwd.
    as_product "$product/deploy" install
    ;;
legacy-retire)
    old_release="$state/releases/$product_name-$bundle-$old_version"
    # Retire only the selected release; compare every other bundle's trust records.
    sudo -n fapolicyd-cli --dump-db | grep -F "$state/releases/myproduct-" | grep -v -F "/myproduct-$bundle-" | sort > "$base/legacy-trust-after"
    cmp "$base/legacy-trust-before" "$base/legacy-trust-after"
    sudo -n fapolicyd-cli --file delete "$old_release/deploy.py" --trust-file "$product_name-$bundle"
    sudo -n fapolicyd-cli --update
    wait_trust "$product/deploy.py" "$old_release/deploy.py"
    sudo -n fapolicyd-cli --dump-db | grep -F "$state/releases/myproduct-" | grep -v -F "/myproduct-$bundle-" | sort > "$base/legacy-trust-after"
    cmp "$base/legacy-trust-before" "$base/legacy-trust-after"
    echo 'PASS: verified own old trust retired, sibling trust unchanged'
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
    # Only app1 is transferred and upgraded; the catalog is still validated.
    ./build-bundle.sh app1
    (cd dist && sha256sum -c "$product_name-app1-$requested_version-offline.tar.gz.sha256")
    cat "build/bundle/$product_name-app1-$requested_version/images/images.txt"
    ;;
help-upgrade-bundle|platform-upgrade-bundle|identity-upgrade-bundle)
    cd "$src"
    [[ $requested_version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
    export HELP_RELEASE_VERSION="$requested_version" RELEASE_KIND="$bundle"
    python3 - <<'HELP_BUILD'
import os
import re
import subprocess
import tempfile
from pathlib import Path
import bundle
from deployment import catalog

version = os.environ["HELP_RELEASE_VERSION"]
source = Path.cwd()
with tempfile.TemporaryDirectory(prefix="myproduct-help-release-") as directory:
    release = Path(directory) / "release"
    subprocess.run(["git", "clone", "--local", "--no-hardlinks", str(source), str(release)], check=True)
    (release / "VERSION").write_text(version + "\n")
    kind = os.environ["RELEASE_KIND"]
    if kind == "help":
        manifest = next((release / "components/help/manifests").glob("*.yaml"))
        text, count = re.subn(r"localhost/myproduct-help:[0-9]+\.[0-9]+\.[0-9]+", "localhost/myproduct-help:" + version, manifest.read_text())
        if count != 1:
            raise SystemExit("FAIL: expected exactly one help image")
        manifest.write_text(text)
        content = release / "apps/help/index.html"
        if "</body>" not in content.read_text():
            raise SystemExit("FAIL: missing help content insertion point")
        content.write_text(content.read_text().replace("</body>", "<p>help-release-" + version + "</p></body>"))
        subprocess.run(["podman", "build", "-t", "localhost/myproduct-help:" + version,
                        "-f", str(release / "apps/help/Containerfile"), str(release / "apps/help")], check=True)
    elif kind == "identity":
        (release / "IDENTITY_VERSION").write_text(version + "\n")
        program = release / "apps/identity/Program.cs"
        marker = 'new { status = "ok" }'
        if program.read_text().count(marker) != 1:
            raise SystemExit("FAIL: expected one Identity health marker")
        program.write_text(program.read_text().replace(marker, 'new { status = "ok", release = "' + version + '" }'))
        manifest = release / "components/identity/manifests/50-identity.yaml"
        text, count = re.subn(r"localhost/myproduct-identity:[0-9]+\.[0-9]+\.[0-9]+", "localhost/myproduct-identity:" + version, manifest.read_text())
        if count != 1:
            raise SystemExit("FAIL: expected one Identity image")
        manifest.write_text(text)
        subprocess.run(["podman", "build", "-t", "localhost/myproduct-identity:" + version,
                        "-f", str(release / "apps/identity/Containerfile"), str(release / "apps/identity")], check=True)
    else:
        (release / "PLATFORM_VERSION").write_text(version + "\n")
    bundle.ROOT = release
    bundle.STAGE = source / "build/help-upgrade"
    bundle.DIST = source / "dist"
    # Compile the release's own catalog entry, exactly as build-bundle.sh would.
    descriptor = catalog.source_descriptors(release)[kind]
    bundle.build_release(descriptor["version"], descriptor)

HELP_BUILD
    (cd dist && sha256sum -c "$product_name-$bundle-$requested_version-offline.tar.gz.sha256")
    cat "build/help-upgrade/$product_name-$bundle-$requested_version/images/images.txt"
    ;;
help-upgrade|platform-upgrade|identity-upgrade)
    prepare_release
    validate_release
    sudo -n -H -u "$product_name" bash -c 'cd "$1" && exec bash ./deploy install' bash "$product"
    healthy
    wait_trust "$product/deployment/"
    if [[ $bundle == help ]]; then test "$(as_product cat "$state/installed/help")" = "$requested_version"; fi
    ;;
identity-before|identity-after)
    as_product python3 - "$action" "$requested_version" <<'IDENTITY_STATE'
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def command(arguments):
    result = subprocess.run(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True, check=False, timeout=30)
    if result.returncode:
        raise RuntimeError("Identity observation failed")
    return result.stdout


def observe():
    root = Path.home() / "identity"
    paths = [root / "config.yaml"] + [path for path in (root / "credentials").rglob("*") if path.is_file()]
    required = ("identity-db/password", "identity/identity.key", "identity/identity.crt")
    if any(not (root / "credentials" / name).is_file() for name in required):
        raise RuntimeError("Missing Identity credential evidence")
    files = {str(path.relative_to(root)): {"hash": hashlib.sha256(path.read_bytes()).hexdigest(), "mode": path.stat().st_mode & 0o777} for path in paths}
    volumes = {}
    for name in ("identity-data", "identity-protection"):
        rows = json.loads(command(["podman", "volume", "inspect", name]))
        if not isinstance(rows, list) or len(rows) != 1:
            raise RuntimeError("Incomplete Identity volume evidence")
        volumes[name] = {key: rows[0][key] for key in ("Name", "Mountpoint", "CreatedAt")}
    rows = json.loads(command(["podman", "inspect", "--format", "json", "identity-server-app"]))
    if not isinstance(rows, list) or len(rows) != 1 or rows[0]["Name"] != "identity-server-app":
        raise RuntimeError("Incomplete Identity image evidence")
    row = rows[0]
    if row["State"]["Status"] != "running" or row["State"]["Health"]["Status"] != "healthy" or not row["Image"]:
        raise RuntimeError("Identity is not healthy")
    return {"files": files, "volumes": volumes, "image": row["Image"].replace("sha256:", ""), "image_name": row["ImageName"]}


def main():
    snapshot = Path.home() / "identity-lifecycle.json"
    state = observe()
    if sys.argv[1] == "identity-before":
        fd = os.open(str(snapshot), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(state, stream)
    else:
        before = json.loads(snapshot.read_text())
        version = sys.argv[2]
        image = "localhost/myproduct-identity:" + version
        if state["files"] != before["files"] or state["volumes"] != before["volumes"]:
            raise RuntimeError("Identity credentials, config or data volumes changed")
        if (Path.home() / "installed/identity").read_text().strip() != version:
            raise RuntimeError("Identity version marker missing")
        image_id = command(["podman", "image", "inspect", "--format", "{{.Id}}", image]).strip().replace("sha256:", "")
        if state["image_name"] != image or state["image"] == before["image"] or state["image"] != image_id:
            raise RuntimeError("Rebuilt Identity image is not actually running")
        result = command(["podman", "exec", "identity-server-app", "bash", "-c",
                          'exec 3<>/dev/tcp/127.0.0.1/8080; printf "GET /identity/health HTTP/1.0\\r\\nHost: localhost\\r\\n\\r\\n" >&3; cat <&3'])
        if '"release":"' + version + '"' not in result:
            raise RuntimeError("New Identity application content is not observable")
    print("PASS: " + sys.argv[1] + "; credential/data/image evidence verified; private values withheld")


try:
    main()
except Exception:
    raise SystemExit("FAIL: Identity lifecycle verification (details withheld)") from None
IDENTITY_STATE
    ;;
help-without-identity)
    healthy
    sudo -n test ! -e "$state/installed/identity"
    sudo -n test ! -e "$state/identity"
    curl --noproxy '*' --cacert <(as_product cat "$state/PKI/private/ca.crt") \
        --resolve "$prod_host:$port:$prod_ip" --fail --silent --show-error --max-time 10 \
        --output /dev/null "https://$prod_host:$port/help/"
    echo 'PASS: platform/help are healthy without Identity installed or DNS-resolvable'
    ;;
platform-before|platform-after|platform-downgrade)
    as_product python3 - "$action" "$state/platform-lifecycle.json" "$product" "$state/releases/$product_name-platform-$old_version" <<'PLATFORM_LIFECYCLE'
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def observe():
    root = Path.home()
    paths = []
    for directory in ("platform", "identity", "app1", "app2", "help", "installed", "routes", "clients", ".config/containers/systemd"):
        paths.extend(path for path in (root / directory).rglob("*") if path.is_file())
    files = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    names = ["platform-proxy-nginx"]
    if sys.argv[1] == "platform-downgrade":
        if (root / "installed/identity").is_file():
            names.extend(["identity-server-app", "identity-postgres-db"])
        for component in ("app1", "app2"):
            if (root / "installed" / component).is_file():
                names.extend([component + "-postgres-db", component + "-todo-backend", component + "-todo-frontend"])
        if (root / "installed/help").is_file():
            names.append("help-web-web")
    containers = {}
    for name in names:
        result = subprocess.run(["podman", "inspect", "--format", "json", name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=True)
        rows = json.loads(result.stdout)
        if len(rows) != 1 or rows[0]["Name"] != name:
            raise SystemExit("FAIL: invalid platform inventory")
        state = rows[0]["State"]
        if state["Status"] != "running" or state["Health"]["Status"] != "healthy" or type(state["Pid"]) is not int or state["Pid"] <= 1 or not isinstance(state["StartedAt"], str) or not state["StartedAt"] or type(rows[0]["RestartCount"]) is not int or rows[0]["RestartCount"] < 0:
            raise SystemExit("FAIL: platform is not healthy")
        containers[name] = {"Pid": state["Pid"], "StartedAt": state["StartedAt"], "RestartCount": rows[0]["RestartCount"]}
    return {"files": files, "containers": containers, "version": (root / "installed/platform").read_text().strip()}


def main():
    action, snapshot, release, old_release = sys.argv[1:]
    current = observe()
    path = Path(snapshot)
    if action == "platform-before":
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(current, stream)
    elif action == "platform-after":
        before = json.loads(path.read_text())
        expected = (Path(release) / "VERSION").read_text().strip()
        if current["version"] != expected or current["version"] == before["version"]:
            raise SystemExit("FAIL: platform version was not upgraded")
        for name, old in before["containers"].items():
            new = current["containers"][name]
            if new["Pid"] == old["Pid"] or new["StartedAt"] == old["StartedAt"]:
                raise SystemExit("FAIL: expected explicit platform restart")
    else:
        # The previous app bundle is still verified/trusted; refuse its older platform.
        result = subprocess.run(["bash", str(Path(old_release) / "deploy"), "install"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False)
        if result.returncode != 1 or "Platform downgrade refused" not in result.stderr or "+ podman" in result.stdout:
            raise SystemExit("FAIL: older platform was not refused before image operations")
        if observe() != current:
            raise SystemExit("FAIL: downgrade refusal changed persistent files or platform processes")
    print("PASS: " + action + "; private state and inspect contents withheld")


try:
    main()
except (OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError):
    raise SystemExit("FAIL: invalid platform lifecycle observation")
PLATFORM_LIFECYCLE
    ;;
help-content)
    content=$(as_product curl --noproxy '*' --cacert "$state/PKI/private/ca.crt" \
        --resolve "$prod_host:$port:$prod_ip" --fail --silent --show-error --max-time 10 "https://$prod_host:$port/help/")
    grep -Fq "help-release-$requested_version" <<< "$content"
    echo 'PASS: new help content served via verified HTTPS'
    ;;
help-retire|platform-retire|identity-retire)
    old_release="$state/releases/$product_name-$bundle-$old_version"
    sudo -n fapolicyd-cli --file delete "$old_release/deployment/" --trust-file "$product_name-$bundle"
    sudo -n fapolicyd-cli --update
    wait_trust "$product/deployment/" "$old_release/deployment/"
    as_product rm -rf -- "$old_release"
    sudo -n test ! -e "$old_release"
    echo "PASS: old $bundle release and its own trust retired after verification"
    ;;
prepare-host)
    cd "$base"
    archive="$product_name-$bundle-$version-offline.tar.gz"
    sha256sum -c "$archive.sha256"
    stage=$(mktemp -d "/tmp/$product_name-host.XXXXXXXX")
    tar xzf "$archive" -C "$stage"
    # The documented host baseline (README, fapolicyd): a subject cache large
    # enough that starting processes are not evicted (backlog 29).
    sudo -n sed -i -E 's/^[[:space:]]*subj_cache_size[[:space:]]*=.*/subj_cache_size = 16381/' /etc/fapolicyd/fapolicyd.conf
    sudo -n grep -qx 'subj_cache_size = 16381' /etc/fapolicyd/fapolicyd.conf \
        || echo 'subj_cache_size = 16381' | sudo -n tee -a /etc/fapolicyd/fapolicyd.conf >/dev/null
    sudo -n systemctl restart fapolicyd
    sudo -n systemctl is-active fapolicyd
    sudo -n bash "$stage/$product_name-$bundle-$version/scripts/prepare-host.sh" --port "$port"
    rm -rf -- "$stage"
    as_product mkdir -p "$state/releases"
    ;;
help-alone)
    prepare_release
    as_product python3 -B - "$product/deploy" <<'HELP_ALONE'
import pathlib
import subprocess
import sys


def main():
    """Require a clean dependency refusal without creating any component state."""
    result = subprocess.run(["bash", sys.argv[1], "install"], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, universal_newlines=True, check=False)
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 1 or result.stderr.strip() != "ERROR: Install the separate platform bundle before installing help":
        raise SystemExit("FAIL: help-alone did not refuse the missing platform")
    home = pathlib.Path.home()
    if any((home / name).exists() for name in ("installed", "platform", "identity", "app1", "app2", "help", "routes", "clients")):
        raise SystemExit("FAIL: help-alone changed persistent component state")
    print("PASS: help-alone refused missing platform without component writes")


main()
HELP_ALONE
    output=$(as_product podman ps -aq)
    test -z "$output"
    ;;
upgrade)
    prepare_release
    old_release="$state/releases/$product_name-$bundle-$old_version"
    validate_release
    sudo -n -H -u "$product_name" bash -c 'cd "$1" && exec bash ./deploy install' bash "$product"
    healthy
    sudo -n fapolicyd-cli --file delete "$old_release/deployment/" --trust-file "$product_name-$bundle"
    sudo -n fapolicyd-cli --update
    wait_trust "$product/deployment/" "$old_release/deployment/"
    echo 'PASS: old own deployment package trust removed; other bundles untouched'
    ;;
persistent-state)
    as_product python3 - <<'HASHES'
import hashlib
import json
import pathlib
import ssl


def main():
    """Hash private persistent files for the controller without printing their contents."""
    root = pathlib.Path.home()
    paths = []
    for component in ("platform", "identity", "app1", "app2", "help"):
        config = root / component / "config.yaml"
        if config.is_file():
            paths.append(config)
        for directory in ("credentials", "files"):
            paths.extend(p for p in (root / component / directory).rglob("*") if p.is_file())
    for directory in ("PKI/private", "routes", "clients"):
        paths.extend(p for p in (root / directory).rglob("*") if p.is_file())
    if not paths:
        raise SystemExit("FAIL: no persistent files")
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    ca = ssl.PEM_cert_to_DER_cert((root / "PKI/private/ca.crt").read_text())
    print(json.dumps({"files_sha256": hashes, "ca_der_sha256": hashlib.sha256(ca).hexdigest()}, sort_keys=True))


main()
HASHES
    ;;
unpack)
    cd "$base"
    archive="$product_name-$bundle-$requested_version-offline.tar.gz"
    sha256sum -c "$archive.sha256"
    tar -xOf "$archive" "$product_name-$bundle-$requested_version/VERSION" > "version-$bundle"
    version=$(cat "version-$bundle")
    test "$version" = "$requested_version"
    [[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
    cat "version-$bundle"
    ;;
registry-offline)
    cd "$base/registry"
    sha256sum -c myproduct-0.0.0-offline.tar.gz.sha256
    tar xzf myproduct-0.0.0-offline.tar.gz
    sudo -n bash -c 'cd "$1" && sha256sum -c --quiet checksums.sha256' bash "$PWD/myproduct-0.0.0"
    as_product podman load -i /dev/stdin < myproduct-0.0.0/images/images.tar
    image=$(cat myproduct-0.0.0/images/images.txt)
    [[ $image =~ ^127\.0\.0\.1:[0-9]+/acceptance/busybox:1\.37\.0$ ]]
    as_product podman image exists "$image"
    as_product podman images --format '{{.Repository}}:{{.Tag}}'
    result=$(as_product podman run --rm --pull=never --network=none "$image" sh -c 'printf registry-offline-ok')
    test "$result" = registry-offline-ok
    echo 'PASS: registry name preserved by save/load; image runs offline with pull=never'
    healthy
    start_date=$(LC_ALL=C date -d "@$run_started" +%x)
    start_time=$(date -d "@$run_started" +%H:%M:%S)
    audit_events check
    ;;
install)
    prepare_release
    install_configuration
    validate_release
    date +%s > "$base/install-start-$bundle"
    sudo -n -H -u "$product_name" bash -c 'cd "$1" && exec bash ./deploy install' bash "$product"
    as_product podman ps --all
    sudo -n -H -u "$product_name" cat "$product/images/images.txt" | while read -r image; do as_product podman image exists "$image"; done
    ;;
database-auth)
    as_product python3 - <<'DATABASE_AUTH'
import json
import pathlib
import subprocess
import sys

# Fixed code only; sibling credentials go over stdin, never argv or generated code.
CHECK = """
import json
import sys
import psycopg
from database import authentication_failed, parameters
try:
    values = parameters()
    with psycopg.connect(**values, connect_timeout=5) as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    values["password"] = json.load(sys.stdin)["sibling_password"]
    try:
        with psycopg.connect(**values, connect_timeout=5) as connection:
            connection.execute("SELECT 1")
    except psycopg.Error as error:
        if not authentication_failed(error):
            raise RuntimeError("Expected authentication failure") from None
    else:
        raise RuntimeError("Sibling password unexpectedly authenticated")
except Exception:
    print("FAIL: database credential check (details withheld)")
    sys.exit(1)
print("PASS: correct secret connects; sibling password authentication rejected")
"""


def logs_safe(home):
    credentials, containers = [], ["identity-server-app", "identity-postgres-db"]
    for component, relative in (("identity", "identity-db"), ("app1", "database"), ("app2", "database")):
        if not (home / "installed" / component).exists():
            continue
        credentials.append((home / component / "credentials" / relative / "password").read_bytes().decode("utf-8").rstrip("\n"))
        if component != "identity":
            containers += [component + "-todo-backend", component + "-postgres-db"]
    for container in containers:
        result = subprocess.run(["podman", "logs", container], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, check=False)
        content = result.stdout + result.stderr
        if result.returncode or any(value in content for value in credentials) or ("password=" in content.lower() and "host=" in content.lower()):
            raise RuntimeError("Database log safety check failed (content withheld)")
    print("PASS: database/client logs contain no database passwords")


def main():
    home = pathlib.Path.home()
    logs_safe(home)
    result = subprocess.run(["podman", "exec", "identity-server-app", "dotnet", "Identity.dll", "--database-check"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False)
    if result.returncode or "verified via ConnectionStrings__Default" not in result.stdout:
        raise RuntimeError("Identity runtime environment connection check failed")
    print("PASS: installed Identity uses ConnectionStrings__Default")
    for component, sibling in (("app1", "app2"), ("app2", "app1")):
        if not (home / "installed" / component).exists() or not (home / "installed" / sibling).exists():
            continue
        password = (home / sibling / "credentials/database/password").read_bytes().decode("utf-8").rstrip("\n")
        result = subprocess.run(["podman", "exec", "-i", component + "-todo-backend", "python", "-c", CHECK],
                                input=json.dumps({"sibling_password": password}), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, check=False)
        if result.returncode or result.stdout.strip() != "PASS: correct secret connects; sibling password authentication rejected":
            raise RuntimeError("Installed app database authentication check failed")
        print("PASS: " + component + " correct secret connects; sibling password authentication rejected")


try:
    main()
except Exception:
    raise SystemExit("FAIL: installed database credentials (details withheld)") from None
DATABASE_AUTH
    ;;
health) healthy;;
check)
    profile
    healthy
    user_service is-active "$product_name-network.service"
    generated=$(as_product /usr/lib/systemd/user-generators/podman-user-generator --dryrun)
    printf '%s\n' "$generated"
    grep -q 'podman-user-wait-network-online.service' <<< "$generated"
    output=$(sudo -n podman ps -aq)
    test -z "$output"
    sudo -n ls -Zd "$state" "$state/.local/share/containers/storage"
    sudo -n env PRODUCT_NAME="$product_name" python3 - <<'PERMISSIONS'
import os
import pathlib
import pwd
import stat


def main():
    """Require private state and readable Quadlets for every installed component."""
    product = os.environ["PRODUCT_NAME"]
    account = pwd.getpwnam(product)
    root = pathlib.Path("/var/lib", product)
    paths = {root: 0o700, root / "PKI/private": 0o700}
    units = root / ".config/containers/systemd"
    paths[units / (product + ".network")] = 0o644
    for marker in (root / "installed").glob("*"):
        component = marker.name
        paths[root / component / "config.yaml"] = 0o600
        for directory in ("credentials", "files"):
            folder = root / component / directory
            if folder.is_dir():
                paths[folder] = 0o700
                for path in folder.rglob("*"):
                    paths[path] = 0o700 if path.is_dir() else 0o600
        paths[units / (product + "-" + component + ".yaml")] = 0o600
        paths[units / (product + "-" + component + ".kube")] = 0o644
    for path, mode in sorted(paths.items()):
        item = path.lstat()
        if (item.st_uid != account.pw_uid or item.st_gid != account.pw_gid
                or stat.S_IMODE(item.st_mode) != mode):
            raise SystemExit("FAIL: private ownership/mode: " + str(path))
        print("PASS: {0}:{0} {1:04o} {2}".format(product, mode, path))


main()
PERMISSIONS
    container_ids=$(as_product podman ps -aq)
    test -n "$container_ids"
    mapfile -t containers <<< "$container_ids"
    upper_dirs=$(as_product podman inspect --format '{{.GraphDriver.Data.UpperDir}}' "${containers[@]}")
    sudo -n env PRODUCT_NAME="$product_name" python3 - "$upper_dirs" <<'LABELS'
import os
import pathlib
import re
import stat
import subprocess
import sys

try:
    import selinux
except ImportError:
    raise SystemExit("FAIL: the selinux Python module is missing; install the host's policycoreutils-python-utils before the snapshot")

HOME = pathlib.Path("/var/lib", os.environ["PRODUCT_NAME"])
STORAGE = HOME / ".local/share/containers/storage"
CUSTOMIZABLE = pathlib.Path("/etc/selinux/targeted/contexts/customizable_types")


def context_type(context):
    """Get the type from an SELinux context and reject an invalid format."""
    parts = context.rstrip("\x00").split(":")
    if len(parts) < 4:
        raise RuntimeError("Invalid SELinux context: " + context)
    return parts[2]


def policy_type(path):
    """Get the policy type using the path's lstat file type; reject errors without fallback."""
    try:
        mode = stat.S_IFMT(os.lstat(str(path)).st_mode)
    except OSError as error:
        raise RuntimeError("lstat failed for {}: {}".format(path, error)) from None
    status, context = selinux.matchpathcon(str(path), mode)
    if status != 0:
        raise RuntimeError("matchpathcon failed: " + str(path))
    return context_type(context)


def check_equivalence():
    """Confirm the container equivalence with policy probes that need no files."""
    probes = ((STORAGE / "overlay-layers", "container_ro_file_t"),
              (STORAGE / "volumes/x/_data/y", "container_file_t"))
    for path, expected in probes:
        status, context = selinux.matchpathcon(str(path), 0)
        if status != 0:
            raise RuntimeError("matchpathcon failed for policy probe: " + str(path))
        actual = context_type(context)
        print("POLICY {} type={} expected={}".format(path, actual, expected))
        if actual != expected:
            raise RuntimeError("The container equivalence is missing or gives the wrong type: " + str(path))


def check_label(path):
    """Log the actual and expected type and reject deviations from the policy."""
    actual = context_type(os.getxattr(str(path), "security.selinux", follow_symlinks=False).decode())
    expected = policy_type(path)
    print("LABEL {} actual={} expected={}".format(path, actual, expected))
    if actual != expected:
        raise RuntimeError("SELinux type deviates from the policy: " + str(path))


def writable_layers(output):
    """Validate UpperDir of existing containers and return their writable layer IDs."""
    layers = set()
    for path in output.splitlines():
        match = re.fullmatch(re.escape(str(STORAGE)) + r"/overlay/([0-9a-f]{64})/diff", path)
        if not match:
            raise RuntimeError("Unexpected UpperDir from podman inspect: " + path)
        layers.add(match.group(1))
    if not layers:
        raise RuntimeError("No writable container layers found")
    return layers


def classify_line(line, customizable, upper_layers):
    """Classify one dry-run line with narrow rules or reject it."""
    proposal = re.fullmatch(r"Would relabel (.+) from (\S+) to (\S+)", line)
    preserved = re.fullmatch(r"(.+) not reset as customized by admin to (\S+)", line)
    if proposal:
        path, before, after = proposal.groups()
        before, after = context_type(before), context_type(after)
    elif preserved:
        path, context = preserved.groups()
        before, after = context_type(context), policy_type(path)
    else:
        raise RuntimeError("Unclassified restorecon line: " + line)
    prefix = str(STORAGE) + "/"
    if not path.startswith(prefix) or ".." in pathlib.Path(path).parts:
        raise RuntimeError("restorecon line outside storage: " + line)
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
        layer = re.fullmatch(r"overlay/([0-9a-f]{64})/diff(?:/.*)?", relative)
        if layer and layer.group(1) in upper_layers and after == "container_ro_file_t":
            return "CUSTOM_WRITABLE_LAYER"
        if re.fullmatch(r"overlay-containers/[0-9a-f]{64}/rootfs/upper(?:/.*)?", relative) and after == "container_var_lib_t":
            return "CUSTOM_WRITABLE_ROOTFS"
    raise RuntimeError("Unclassified restorecon line: " + line)


def dryrun(arguments):
    """Log read-only restorecon output and reject the command's failing status."""
    result = subprocess.run(["restorecon", "-n", "-v", "-R"] + arguments,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True, check=False)
    print("$ restorecon -n -v -R " + " ".join(arguments))
    print(result.stdout, end="")
    print(result.stderr or "", end="", file=sys.stderr)
    if result.returncode:
        raise RuntimeError("restorecon dry-run failed: exit " + str(result.returncode))
    if result.stderr:
        raise RuntimeError("restorecon dry-run wrote diagnostics to stderr")
    return result.stdout


def main():
    """Check policy, actual labels and the classified dry run without relabeling."""
    check_equivalence()
    upper_layers = writable_layers(sys.argv[1])
    for layer in sorted(upper_layers):
        print("WRITABLE_LAYER " + layer)
    for name in ("", "overlay", "overlay-layers", "overlay-images", "overlay-containers", "volumes"):
        check_label(STORAGE / name)
    volumes = sorted((STORAGE / "volumes").glob("*/_data"))
    if not volumes:
        raise RuntimeError("No volume data found")
    for root in volumes:
        check_label(root)
        for directory, dirs, files in os.walk(str(root)):
            for name in sorted(dirs + files):
                check_label(pathlib.Path(directory) / name)
    outputs, failures = [], []
    # Both dry runs are read-only evidence, even when the first one reports an error.
    for arguments in (["-e", str(STORAGE), str(HOME)], [str(STORAGE)]):
        try:
            outputs.append(dryrun(arguments))
        except RuntimeError as error:
            outputs.append("")
            failures.append(str(error))
    if failures:
        raise RuntimeError("; ".join(failures))
    outside, inside = outputs
    if outside:
        raise RuntimeError("restorecon proposes changes outside storage")
    customizable = set(CUSTOMIZABLE.read_text().splitlines())
    for line in inside.splitlines():
        rule = classify_line(line, customizable, upper_layers)
        print("RULE {}: {}".format(rule, line))
    print("PASS: policy, actual labels and classified restorecon dry run")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        raise SystemExit("FAIL: " + str(error))
LABELS
    start_date=$(LC_ALL=C date -d "@$run_started" +%x)
    start_time=$(date -d "@$run_started" +%H:%M:%S)
    audit_events check
    as_product python3 - <<'CREDENTIAL_FILES'
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path.home()
NAMES = ("session-key", "todo-client.key", "todo-client.crt", "ca.crt")
# Fixed code only: no source bytes, credentials or configuration in argv/logs.
PROBE = r"""
import errno
import hashlib
import json
import os
import stat
from pathlib import Path

files = {}
for path in sorted(Path("/certificates").iterdir()):
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise SystemExit(1)
    files[path.name] = {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "gid": info.st_gid,
    }
    try:
        descriptor = os.open(str(path), os.O_WRONLY)
    except OSError as error:
        if error.errno != errno.EROFS:
            raise SystemExit(1)
    else:
        os.close(descriptor)
        raise SystemExit(1)
print(json.dumps(files, sort_keys=True))
"""


def main():
    """Check actual app credential bytes, mode, ownership and read-only/backend isolation."""
    for component in ("app1", "app2"):
        if not (ROOT / "installed" / component).is_file():
            continue
        expected = {}
        for name in NAMES:
            source = ROOT / component / "credentials/todo" / name
            expected[name] = {
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "mode": 0o400, "uid": 0, "gid": 0,
            }
        result = subprocess.run(
            ["podman", "exec", component + "-todo-backend", "python", "-c", PROBE],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=20,
        )
        if result.returncode or json.loads(result.stdout) != expected:
            raise RuntimeError("Backend credential content, mode or ownership mismatch")
        frontend = subprocess.run(
            ["podman", "inspect", "--format", "{{json .Mounts}}", component + "-todo-frontend"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=10,
        )
        if frontend.returncode:
            raise RuntimeError("Cannot inspect frontend credential isolation")
        for mount in json.loads(frontend.stdout) or []:
            destination = mount["Destination"].rstrip("/")
            if destination == "/certificates" or destination.startswith("/certificates/") or destination == "/run/secrets" or destination.startswith("/run/secrets/"):
                raise RuntimeError("Frontend has a credential mount")
        if (ROOT / component / "files" / (component + "-signing.tar")).exists():
            raise RuntimeError("Unexpected app credential import archive in fresh state")
        print("PASS: " + component + " credentials match private read-only backend files; no frontend mount")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired):
        raise SystemExit("FAIL: app credential delivery check failed; details withheld")
CREDENTIAL_FILES
    components=$(installed_components)
    for component in $components; do
        if [[ $component == app1 || $component == app2 ]]; then
            as_product podman exec "$component-todo-backend" python -c "import socket; socket.create_connection(('$component-postgres',5432),5).close()"
        fi
    done
    as_product podman exec platform-proxy-nginx wget -qO- http://identity-server:8080/identity/.well-known/openid-configuration
    # Only matching pull evidence, not arbitrary application logs with auth data.
    uid=$(id -u "$product_name")
    journal=$(sudo -n journalctl _UID="$uid" --since "@$run_started" --no-pager)
    if grep -Ei 'Trying to pull|Pulling image|pull access denied' <<< "$journal"; then
        echo 'FAIL: install attempted a pull'; exit 1
    fi
    echo 'PASS: journal contains no pull attempts'
    ;;
prod-e2e|markers-create|markers-check|shared-login|survivor-e2e|survivor-markers|app1-e2e|app1-markers-create|app1-markers-check)
    cd "$src"
    export PUBLIC_ORIGIN="https://$prod_host:$port" CONNECT_IP="$prod_ip"
    export SMOKE_CA_FILE="$private/ca.crt" SMOKE_PASSWORD_DIR="$private"
    if [[ $action == shared-login ]]; then
        .venv-smoke/bin/python acceptance/shared_login.py
    else
        apps="app1 app2"
        if [[ $action == survivor-* ]]; then apps=app2; fi
        if [[ $action == app1-* ]]; then apps=app1; fi
        for app in $apps; do
            export APP_BASE_PATH=/$app
            if [[ $action == prod-e2e || $action == survivor-e2e || $action == app1-e2e ]]; then
                .venv-smoke/bin/python dev/smoke-test.py
            else
                operation=${action#app1-}
                operation=${operation#markers-}
                if [[ $action == survivor-markers ]]; then operation=check; fi
                .venv-smoke/bin/python acceptance/markers.py "$operation" "$base/markers-$app.json" "$run"
            fi
        done
    fi
    ;;
stop)
    components=$(installed_components)
    for component in $components; do user_service stop "$product_name-$component.service"; done
    output=$(as_product podman ps -q)
    test -z "$output"
    as_product podman secret ls
    as_product podman volume ls
    ;;
start|restart)
    components=$(installed_components)
    for component in $components; do user_service "$action" "$product_name-$component.service"; done
    healthy
    ;;
crash)
    python3 - <<'CRASH'
import json
import os
import shlex
import subprocess
import sys
import time

CONTAINER = "app1-todo-backend"


def product_command(arguments):
    """Build a Podman call as the service user from the right home and runtime."""
    return ["sudo", "-n", "-H", "-u", os.environ["PRODUCT_NAME"], "bash", "-c",
            'cd "$HOME" || exit; export XDG_RUNTIME_DIR="/run/user/$(id -u)"; exec "$@"',
            "bash"] + arguments


def command(arguments):
    """Return stdout without logging inspect content and keep stderr also on failure."""
    print("$ " + " ".join(shlex.quote(arg) for arg in arguments))
    result = subprocess.run(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True, check=False, timeout=10)
    print(result.stderr or "", end="", file=sys.stderr)
    if result.returncode:
        raise RuntimeError("Crash test command failed: exit " + str(result.returncode))
    return result.stdout


def inspect_container():
    """Parse inspect JSON and validate only the fields the check uses."""
    try:
        template = ('[{"State":{"Pid":{{.State.Pid}},"Running":{{.State.Running}},'
                    '"StartedAt":{{json .State.StartedAt}},'
                    '"StoppedByUser":{{.State.StoppedByUser}},'
                    '"Health":{"Status":{{json .State.Health.Status}}}},'
                    '"RestartCount":{{.RestartCount}}}]')
        rows = json.loads(command(product_command(["podman", "inspect", "--format", template, CONTAINER])))
        if not isinstance(rows, list) or len(rows) != 1:
            raise ValueError("Expected one container")
        state = rows[0]["State"]
        result = {"Pid": state["Pid"], "Running": state["Running"],
                  "StartedAt": state["StartedAt"], "RestartCount": rows[0]["RestartCount"],
                  "StoppedByUser": state["StoppedByUser"]}
        if (type(result["Pid"]) is not int or result["Pid"] < 0
                or type(result["Running"]) is not bool
                or (result["Running"] and result["Pid"] <= 1)
                or type(result["RestartCount"]) is not int or result["RestartCount"] < 0
                or type(result["StoppedByUser"]) is not bool
                or not isinstance(result["StartedAt"], str) or not result["StartedAt"].strip()):
            raise ValueError("Invalid state fields")
    except (ValueError, KeyError, TypeError):
        raise RuntimeError("Invalid or empty container state from inspect") from None
    return result


def main():
    """Kill the host process once and require one automatic restart within 60 seconds."""
    before = inspect_container()
    if not before["Running"] or before["StoppedByUser"]:
        raise RuntimeError("The container must be running and not stopped by the user before the crash test")
    print("BEFORE " + json.dumps(before, sort_keys=True))
    command(["sudo", "-n", "kill", "-KILL", str(before["Pid"])])
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        after = inspect_container()
        print("AFTER " + json.dumps(after, sort_keys=True))
        if after["StoppedByUser"]:
            raise RuntimeError("StoppedByUser was set during the crash test")
        if after["RestartCount"] > before["RestartCount"] + 1:
            raise RuntimeError("The container restarted more than once")
        if (after["Running"] and after["RestartCount"] == before["RestartCount"] + 1
                and after["Pid"] != before["Pid"] and after["StartedAt"] != before["StartedAt"]):
            print("PASS: one automatic restart with a new PID and start time after the process crash")
            return
        time.sleep(min(2, max(0, deadline - time.monotonic())))
    raise RuntimeError("No verified automatic restart within 60s")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        raise SystemExit("FAIL: " + str(error))
CRASH
    healthy
    wait_backend
    ;;
hang)
    python3 - <<'HANG'
import json
import os
import shlex
import subprocess
import sys
import time

CONTAINER = "app1-todo-backend"


def product_command(arguments):
    """Build a Podman call as the service user from the right home and runtime."""
    return ["sudo", "-n", "-H", "-u", os.environ["PRODUCT_NAME"], "bash", "-c",
            'cd "$HOME" || exit; export XDG_RUNTIME_DIR="/run/user/$(id -u)"; exec "$@"',
            "bash"] + arguments


def command(arguments):
    """Return stdout without logging inspect content and keep stderr also on failure."""
    print("$ " + " ".join(shlex.quote(arg) for arg in arguments))
    result = subprocess.run(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True, check=False, timeout=10)
    print(result.stderr or "", end="", file=sys.stderr)
    if result.returncode:
        raise RuntimeError("Hang test command failed: exit " + str(result.returncode))
    return result.stdout


def inspect_container():
    """Parse inspect JSON and validate the hang test state fields."""
    try:
        template = ('[{"State":{"Pid":{{.State.Pid}},"Running":{{.State.Running}},'
                    '"StartedAt":{{json .State.StartedAt}},'
                    '"StoppedByUser":{{.State.StoppedByUser}},'
                    '"Health":{"Status":{{json .State.Health.Status}}}},'
                    '"RestartCount":{{.RestartCount}}}]')
        rows = json.loads(command(product_command(["podman", "inspect", "--format", template, CONTAINER])))
        if not isinstance(rows, list) or len(rows) != 1:
            raise ValueError("Expected one container")
        state = rows[0]["State"]
        result = {"Pid": state["Pid"], "Running": state["Running"],
                  "StartedAt": state["StartedAt"], "RestartCount": rows[0]["RestartCount"],
                  "StoppedByUser": state["StoppedByUser"],
                  "Health": state["Health"]["Status"]}
        if (type(result["Pid"]) is not int or result["Pid"] < 0
                or type(result["Running"]) is not bool
                or (result["Running"] and result["Pid"] <= 1)
                or type(result["RestartCount"]) is not int or result["RestartCount"] < 0
                or type(result["StoppedByUser"]) is not bool
                or result["Health"] not in ("healthy", "starting", "unhealthy")
                or not isinstance(result["StartedAt"], str) or not result["StartedAt"].strip()):
            raise ValueError("Invalid state fields")
    except (ValueError, KeyError, TypeError):
        raise RuntimeError("Invalid or empty container state from inspect") from None
    return result


def main():
    """Freeze all host processes once and require unhealthy followed by one healthy restart."""
    before = inspect_container()
    if not before["Running"] or before["StoppedByUser"] or before["Health"] != "healthy":
        raise RuntimeError("The container must be healthy before the hang test")
    print("BEFORE " + json.dumps(before, sort_keys=True), flush=True)
    top = command(product_command(["podman", "top", CONTAINER, "hpid"]))
    lines = top.splitlines()
    if not lines or lines[0].strip().upper() != "HPID":
        raise RuntimeError("Invalid PID list from podman top")
    pids = [line.strip() for line in lines[1:]]
    if (not pids or any(not pid.isdigit() or int(pid) <= 1 for pid in pids)
            or len(set(pids)) != len(pids) or str(before["Pid"]) not in pids):
        raise RuntimeError("Invalid host PIDs from podman top")
    for pid in pids:
        command(["sudo", "-n", "kill", "-STOP", pid])
    deadline, unhealthy = time.monotonic() + 300, False
    while time.monotonic() < deadline:
        after = inspect_container()
        print("AFTER " + json.dumps(after, sort_keys=True), flush=True)
        unhealthy = unhealthy or after["Health"] == "unhealthy"
        stopping_original = (
            after["Health"] == "unhealthy" and not after["Running"]
            and after["RestartCount"] == before["RestartCount"]
            and after["StartedAt"] == before["StartedAt"]
            and after["Pid"] in (0, before["Pid"])
        )
        # A health-triggered Stop sets this flag before cleanup restarts the container.
        if after["StoppedByUser"] and not stopping_original:
            raise RuntimeError("StoppedByUser outside the original unhealthy stop phase")
        if after["RestartCount"] > before["RestartCount"] + 1:
            raise RuntimeError("The container restarted more than once")
        if (unhealthy and after["Running"] and not after["StoppedByUser"]
                and after["Health"] == "healthy"
                and after["RestartCount"] == before["RestartCount"] + 1
                and after["Pid"] != before["Pid"] and after["StartedAt"] != before["StartedAt"]):
            print("PASS: unhealthy followed by one automatic restart to healthy")
            return
        time.sleep(min(2, max(0, deadline - time.monotonic())))
    raise RuntimeError("No verified healthy restart after the hang within 300s")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        raise SystemExit("FAIL: " + str(error))
HANG
    healthy
    wait_backend
    ;;
siblings-before|siblings-after|help-siblings-before|help-siblings-after|platform-siblings-before|platform-siblings-after|identity-siblings-before|identity-siblings-after)
    observation="$base/siblings.json"
    if [[ $action == platform-siblings-* ]]; then observation="$base/platform-siblings.json"; fi
    mode=app1
    if [[ $action == platform-siblings-* ]]; then mode=platform; fi
    if [[ $action == identity-siblings-* ]]; then observation="$base/identity-siblings.json"; mode=identity; fi
    if [[ $action == help-* ]]; then observation="$base/help-siblings.json"; mode=help; fi
    sudo -n env PRODUCT_NAME="$product_name" python3 - "$action" "$observation" "$mode" <<'SIBLINGS'
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

PRODUCT = os.environ["PRODUCT_NAME"]
HOME = pathlib.Path("/var/lib", PRODUCT)


def command(arguments):
    """Read separate command streams without printing private inspect or trust content."""
    result = subprocess.run(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True, check=False, timeout=15)
    print(result.stderr, end="", file=sys.stderr)
    if result.returncode:
        raise SystemExit("FAIL: sibling observation command failed")
    return result.stdout


def observe():
    """Project sibling process identity, version markers and their exact trust records."""
    prefix = ["sudo", "-n", "-H", "-u", PRODUCT, "bash", "-c",
              'cd "$HOME" || exit; export XDG_RUNTIME_DIR="/run/user/$(id -u)"; exec "$@"', "bash"]
    mode = sys.argv[3] if len(sys.argv) > 3 else "app1"
    components = {"app1": ["platform", "identity", "app2", "help"],
                  "help": ["platform", "identity", "app1", "app2"],
                  "platform": ["identity", "app1", "app2", "help"],
                  "identity": ["platform", "app1", "app2", "help"]}[mode]
    components = [name for name in components if pathlib.Path(HOME, "installed", name).is_file()]
    names = []
    for component in components:
        if component == "platform":
            names.append("platform-proxy-nginx")
        elif component == "identity":
            names.extend(["identity-postgres-db", "identity-server-app"])
        elif component == "help":
            names.append("help-web-web")
        else:
            names.extend([component + "-postgres-db", component + "-todo-backend", component + "-todo-frontend"])
    rows = json.loads(command(prefix + ["podman", "inspect", "--format", "json"] + names))
    if not isinstance(rows, list) or len(rows) != len(names):
        raise SystemExit("FAIL: incomplete sibling inspect list")
    observed = {}
    for row in rows:
        name, state = row["Name"], row["State"]
        if (name not in names or name in observed or state["Status"] != "running"
                or state["Health"]["Status"] != "healthy"
                or type(row["RestartCount"]) is not int
                or type(state["Pid"]) is not int or state["Pid"] <= 1
                or not isinstance(state["StartedAt"], str) or not state["StartedAt"]):
            raise SystemExit("FAIL: invalid sibling state")
        observed[name] = {"Pid": state["Pid"], "StartedAt": state["StartedAt"], "RestartCount": row["RestartCount"]}
    trust = command(["fapolicyd-cli", "--dump-db"])
    records = sorted(line for line in trust.splitlines()
                     if any("/releases/" + PRODUCT + "-" + component + "-" in line for component in components))
    expected = set()
    for component in components:
        version = pathlib.Path(HOME, "installed", component).read_text().strip()
        package = HOME / "releases" / (PRODUCT + "-" + component + "-" + version) / "deployment"
        files = [str(path) for path in package.rglob("*") if path.is_file()]
        if not files:
            raise SystemExit("FAIL: missing sibling deployment package")
        expected.update(files)
    trusted = []
    for record in records:
        match = re.fullmatch(r"\S+ (/.+) [0-9]+ [0-9a-fA-F]{64}", record)
        if not match:
            raise SystemExit("FAIL: invalid sibling trust entry")
        trusted.append(match.group(1))
    if set(trusted) != expected or len(trusted) != len(expected):
        raise SystemExit("FAIL: expected exact package trust for sibling bundles")
    versions = {name: (HOME / "installed" / name).read_text()
                for name in components}
    result = {"containers": observed, "trust": records, "versions": versions}
    if components:
        root = HOME
        files = []
        for component in components:
            files.append(root / component / "config.yaml")
            for directory in ("credentials", "files"):
                files.extend(path for path in (root / component / directory).rglob("*") if path.is_file())
            for suffix in (".yaml", ".kube"):
                files.append(root / ".config/containers/systemd" / (PRODUCT + "-" + component + suffix))
        result["state"] = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
        network = json.loads(command(prefix + ["podman", "network", "inspect", PRODUCT]))
        if not isinstance(network, list) or len(network) != 1 or not network[0].get("id"):
            raise SystemExit("FAIL: invalid shared network observation")
        result["network"] = network[0]["id"]
    return result


def main():
    """Compare untouched app2/help process identities, version markers and trust entries."""
    path = pathlib.Path(sys.argv[2])
    current = observe()
    if sys.argv[1].endswith("siblings-before"):
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(current, stream)
    elif json.loads(path.read_text()) != current:
        raise SystemExit("FAIL: sibling/platform process identity, version, state, network or trust changed")
    print("SIBLINGS " + json.dumps(current["containers"], sort_keys=True))
    print("PASS: sibling versions and trust " + ("recorded" if sys.argv[1].endswith("siblings-before") else "unchanged"))


try:
    main()
except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired):
    raise SystemExit("FAIL: invalid or incomplete sibling observation")
SIBLINGS
    ;;
uninstall)
    sudo -n -H -u "$product_name" bash -c 'cd "$1" && exec bash ./deploy uninstall' bash "$product"
    sudo -n fapolicyd-cli --file delete "$product/deployment/" --trust-file "$product_name-app1"
    sudo -n fapolicyd-cli --update
    app2_version=$(sudo -n -H -u "$product_name" cat "$state/installed/app2")
    wait_trust "$state/releases/$product_name-app2-$app2_version/deployment/" "$product/deployment/"
    sudo -n test ! -e "$state/installed/app1"
    sudo -n test ! -e "$state/routes/app1.conf"
    sudo -n test ! -e "$state/clients/app1"
    sudo -n test -f "$state/app1/config.yaml"
    as_product podman volume exists app1-data
    as_product podman network exists "$product_name"
    healthy
    http=$(as_product curl --noproxy '*' --cacert "$state/PKI/private/ca.crt" \
        --resolve "$prod_host:$port:$prod_ip" --silent --show-error --max-time 5 \
        --output /dev/null --write-out '%{http_code}' "https://$prod_host:$port/app1/")
    test "$http" = 404
    echo 'PASS: app1 removed, route inactive, data/network retained; app2/help healthy'
    ;;
reboot)
    cat /proc/sys/kernel/random/boot_id
    sudo -n systemd-run --on-active=3 /usr/bin/systemctl reboot
    ;;
boot) cat /proc/sys/kernel/random/boot_id;;
wait-boot-service) wait_boot_service;;
audit|audit-check|launch-audit-check)
    diagnostic_status=0
    health_launch_diagnostics || diagnostic_status=$?
    # Use VM local time for ausearch, derived from the recorded controller epoch.
    start_date=$(LC_ALL=C date -d "@$run_started" +%x)
    start_time=$(date -d "@$run_started" +%H:%M:%S)
    printf 'FANOTIFY/AVC evidence since %s %s (VM local time)\n' "$start_date" "$start_time"
    sudo -n systemctl is-active auditd
    if [[ $action == audit ]]; then audit_events collect; else audit_events check; fi
    if [[ $role == PROD ]]; then
        # Evidence for backlog 29: early evictions can trigger ld.so pattern denials.
        # Every audit action reports them; a clean run uses audit-check, not audit.
        # stdin is this script (bash -se), so keep the CLI away from it.
        fapolicyd_status=$(sudo -n fapolicyd-cli --check-status </dev/null 2>&1) || true
        grep -E '^(q_size|Inter-thread max queue depth|Subject cache size|Subject slots in use|Subject evictions|Early subject cache evictions):' <<< "$fapolicyd_status" \
            || echo "FAPOLICYD_STATUS unavailable: ${fapolicyd_status:0:200}"
    fi
    test "$diagnostic_status" = 0
    ;;
cleanup) rm -rf -- "$private"; test ! -e "$private";;
*) echo "Unknown action: $action" >&2; exit 2;;
esac
