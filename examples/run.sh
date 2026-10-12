#!/usr/bin/env bash
# Isolated dev tests. No sudo, systemd or production installation.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
if [[ $# != 1 ]]; then
    echo "Usage: $0 basic|secrets|volumes|init-containers|manifest-defined|failures" >&2
    exit 2
fi
example=$1
case "$example" in
    basic|secrets|volumes|init-containers|manifest-defined|failures) ;;
    *) echo "Unknown example: $example" >&2; exit 2 ;;
esac
work=$(mktemp -d "${TMPDIR:-/tmp}/offline-example.XXXXXXXX")
run_id="offline-$(basename "$work" | tr '[:upper:].' '[:lower:]-')"
attempted_play=0
volumes=()
secrets=()
cleanup() {
    status=$?
    trap - EXIT
    if [[ $attempted_play == 1 ]]; then
        if ! podman kube down "$work/build/install.yaml"; then
            echo "Cleanup failed: kube down ($work)" >&2
            status=1
        fi
        # Secret mounts can also leave named volumes with the Secret's name.
        for name in "${volumes[@]}" "${secrets[@]}"; do
            if podman volume exists "$name"; then
                podman volume rm "$name" || status=1
            fi
        done
        for name in "${secrets[@]}"; do
            if podman secret inspect "$name" >/dev/null 2>&1; then
                podman secret rm "$name" || status=1
            fi
        done
        if podman pod exists "$run_id"; then
            echo "Cleanup failed: pod $run_id still exists" >&2
            status=1
        fi
    fi
    if [[ $status != 0 && $attempted_play == 1 ]]; then
        echo "Example failed (Podman $(podman --version)); see command output above." >&2
    fi
    rm -rf -- "$work"
    if [[ $status == 0 ]]; then echo "PASS: $example (including cleanup)"; fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
cp "$root/deploy" "$root/deploy.py" "$work/"
# prepare does not read images/quadlet. Allow the supplied partial checkout too.
for dir in images quadlet; do
    if [[ -d "$root/$dir" ]]; then
        cp -R "$root/$dir" "$work/"
    else
        echo "Note: $root/$dir is missing; prepare does not use it." >&2
        mkdir "$work/$dir"
    fi
done
copy_example() {
    local source=$1
    cp "$source/config.yaml" "$work/"
    cp -R "$source/manifests" "$work/"
    if [[ -d "$source/files" ]]; then cp -R "$source/files" "$work/"; fi
    python3 - "$work" "$run_id" "${EXAMPLE_PORT:-18080}" <<'PY'
from pathlib import Path
import sys
root, name, port = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
for path in [root / 'config.yaml'] + list((root / 'manifests').glob('*.yaml')):
    path.write_text(path.read_text().replace('example-run', name))
with (root / 'config.yaml').open('a') as stream:
    stream.write('POD_NAME: ' + name + '\n')
# Replace the existing port, avoiding duplicate config keys.
path = root / 'config.yaml'
path.write_text(path.read_text().replace('HTTPS_PORT: 18080', 'HTTPS_PORT: ' + str(port)))
PY
}
cd "$work"
if [[ $example == failures ]]; then
    for case_dir in "$root/examples/failures/"*/; do
        rm -rf manifests files build
        copy_example "$case_dir"
        if [[ $(basename "$case_dir") == large-secret ]]; then
            mkdir -p files
            python3 -c 'from pathlib import Path; Path("files/large.bin").write_bytes(b"x" * 400000)'
        fi
        if ./deploy prepare >prepare.log 2>&1; then
            echo "FAIL: $(basename "$case_dir") unexpectedly succeeded" >&2
            exit 1
        fi
        expected=$(sed "s/example-run/$run_id/g" "$case_dir/expected-error.txt")
        if ! grep -F -- "$expected" prepare.log; then
            cat prepare.log >&2
            echo "FAIL: wrong error for $(basename "$case_dir")" >&2
            exit 1
        fi
        test ! -e build/install.yaml
        test ! -e build/files
        echo "PASS: $(basename "$case_dir")"
    done
    exit 0
fi
copy_example "$root/examples/$example"
if [[ $example == secrets ]]; then
    python3 -c 'from pathlib import Path; Path("files/binary.bin").write_bytes(bytes(range(256)) * 4 + b"\x00\xff\r\n")'
fi
./deploy prepare
# Only names in this run's rendered document are eligible for cleanup.
mapfile -t volumes < <(python3 -c 'import yaml; print("\n".join(d["metadata"]["name"] for d in yaml.safe_load_all(open("build/install.yaml")) if d.get("kind") == "PersistentVolumeClaim"))' | sed '/^$/d')
mapfile -t secrets < <(python3 -c 'import yaml; print("\n".join(d["metadata"]["name"] for d in yaml.safe_load_all(open("build/install.yaml")) if d.get("kind") == "Secret"))' | sed '/^$/d')
podman image exists localhost/offline-example:1 || {
    echo "Missing localhost/offline-example:1. Follow examples/README.md setup." >&2
    exit 1
}
container="$run_id-app"
play() {
    attempted_play=1
    podman kube play --replace build/install.yaml
}
wait_exec() {
    local i
    for i in {1..30}; do
        if podman exec "$container" "$@"; then return 0; fi
        sleep 1
    done
    podman logs "$container" >&2 || true
    echo "Timed out waiting for container verification" >&2
    return 1
}
check_hash() {
    local source=$1 target=$2 expected actual
    expected=$(sha256sum "$source")
    expected=${expected%% *}
    actual=$(podman exec "$container" sha256sum "$target")
    actual=${actual%% *}
    [[ $expected == "$actual" ]] || { echo "Hash mismatch: $target" >&2; return 1; }
}
play
wait_exec true
case "$example" in
    basic)
        wait_exec sh -ec 'test "$GREETING" = "hello from config"; test "$NUMBER" = 42'
        body=$(curl --fail --silent --show-error --noproxy '*' --retry 15 --retry-connrefused --retry-delay 1 --max-time 3 "http://127.0.0.1:${EXAMPLE_PORT:-18080}/")
        [[ $body == "hello from config|42|${EXAMPLE_PORT:-18080}" ]]
        binding=$(podman port "$container" 8080/tcp)
        [[ $binding == "127.0.0.1:${EXAMPLE_PORT:-18080}" ]]
        ;;
    secrets)
        for path in files/text/*; do check_hash "$path" "/inputs/text/$(basename "$path")"; done
        check_hash files/binary.bin /inputs/binary/binary.bin
        check_hash files/text/message.txt /inputs/selected/renamed.txt
        podman exec "$container" sh -ec '
            test ! -e /inputs/selected/message.txt
            test ! -e /inputs/selected/second.txt'
        echo 'PASS: secret items preserve binary bytes, rename paths and exclude unlisted keys'
        ;;
    volumes)
        for pair in 'files/single.txt /data/single.txt' 'files/tree/top.txt /data/top.txt' 'files/tree/nested/leaf.txt /data/nested/leaf.txt' 'files/tree/nested/run.sh /data/nested/run.sh'; do
            read -r source target <<< "$pair"
            check_hash "$source" "$target"
        done
        podman exec "$container" sh -ec '
            test ! -e /data/tree
            test "$(stat -c "%u:%g:%a" /data/single.txt)" = 0:0:644
            test "$(stat -c "%u:%g:%a" /data/nested)" = 0:0:755
            test "$(stat -c "%u:%g:%a" /data/nested/run.sh)" = 0:0:755
            printf "persistent app data\n" > /data/app-created.txt
            printf "modified by app\n" > /data/single.txt'
        podman kube down build/install.yaml
        printf 'updated upload\n' > files/single.txt
        ./deploy prepare
        play
        wait_exec true
        podman exec "$container" sh -ec 'test "$(cat /data/app-created.txt)" = "persistent app data"'
        echo 'PASS: app-created file persisted across down/play'
        check_hash files/single.txt /data/single.txt
        echo 'PASS: imported file replaced on second play'
        ;;
    init-containers)
        wait_exec sh -ec 'test "$(cat /tmp/observed)" = "$(printf "first\nsecond")"'
        ;;
    manifest-defined)
        wait_exec sh -ec 'test "$TOKEN" = synthetic-example-value; test "$(cat /data/token-seen)" = "$TOKEN"'
        ;;
esac
