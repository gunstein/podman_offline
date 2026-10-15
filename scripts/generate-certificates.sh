#!/usr/bin/env bash
# Generate the demo CA, certificates and passwords without replacing existing keys.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
umask 077
if [[ ${1:-} == --root ]]; then
    if [[ $# -lt 2 || -z $2 ]]; then
        echo 'Usage: scripts/generate-certificates.sh [--root DIR] [DNS hostname]' >&2
        exit 2
    fi
    root=$2
    shift 2
fi
if [[ ${1:-} == core ]]; then
    echo 'ERROR: core was renamed to platform; retained core installations require a separate migration procedure' >&2
    exit 2
fi
if [[ ${1:-} == platform || ${1:-} == app1 || ${1:-} == app2 || ${1:-} == help ]]; then
    component=$1
    shift
    hostname=${1:-myproduct-proxy}
    [[ $# -le 1 && $hostname =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]] || {
        echo 'Usage: generate-certificates.sh [--root DIR] platform|app1|app2|help [DNS hostname]' >&2; exit 2;
    }
    # Refuse both old and mixed layouts before creating any CA/certificate material.
    runtime=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
    for old in "$root/core" "$root/installed/core" \
        "$root/.config/containers/systemd/myproduct-core.kube" \
        "$root/.config/containers/systemd/myproduct-core.yaml" \
        "$root/.config/systemd/user/myproduct-core.service" \
        "$runtime/systemd/generator/myproduct-core.service" \
        "$runtime/systemd/generator.early/myproduct-core.service" \
        "$runtime/systemd/generator.late/myproduct-core.service"; do
        if [[ -e $old || -L $old ]]; then
            echo 'ERROR: legacy core layout requires a separate migration procedure; no certificates changed' >&2
            exit 1
        fi
    done
    command -v podman >/dev/null || {
        echo 'ERROR: cannot check legacy core volumes without Podman; no certificates changed' >&2; exit 1;
    }
    for old in core-identity-data core-identity-protection core-routes core-clients; do
        status=0
        timeout 30 podman volume exists "$old" >/dev/null 2>&1 || status=$?
        if [[ $status != 1 ]]; then
            echo 'ERROR: legacy core volume present or volume check failed; no certificates changed' >&2
            exit 1
        fi
    done
    mkdir -p "$root/PKI/private" "$root/$component/generated-certificates"
    chmod 700 "$root/PKI" "$root/PKI/private" "$root/$component" "$root/$component/generated-certificates"
    cd "$root"
    if [[ -e PKI/private/ca.key || -e PKI/private/ca.crt ]]; then
        [[ -s PKI/private/ca.key && -s PKI/private/ca.crt ]] || {
            echo 'ERROR: incomplete existing CA; do not regenerate it' >&2; exit 1;
        }
    else
        openssl req -x509 -newkey rsa:3072 -nodes -sha256 -days 3650 \
            -keyout PKI/private/ca.key -out PKI/private/ca.crt \
            -subj '/CN=MyProduct Development CA' \
            -addext 'basicConstraints=critical,CA:TRUE' -addext 'keyUsage=critical,keyCertSign,cRLSign'
    fi
    # Issue missing pairs once; a partial existing pair requires operator investigation.
    issue_component() {
        local name=$1 dir=$2 usage=$3 record="PKI/private/$component-$1"
        mkdir -p "$dir"
        chmod 700 "$dir"
        if [[ -e $dir/$name.key || -e $dir/$name.crt ]]; then
            [[ -s $dir/$name.key && -s $dir/$name.crt ]] || {
                echo "ERROR: incomplete existing certificate pair: $dir/$name" >&2; exit 1;
            }
            return
        fi
        openssl req -new -newkey rsa:2048 -nodes -sha256 \
            -keyout "$dir/$name.key" -out "$record.csr" -subj "/CN=$component-$name"
        printf 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n%s\n' "$usage" > "$record.ext"
        openssl x509 -req -in "$record.csr" -CA PKI/private/ca.crt -CAkey PKI/private/ca.key \
            -CAcreateserial -days 365 -sha256 -extfile "$record.ext" -out "$dir/$name.crt"
    }
    # Preserve existing passwords and refuse empty files rather than rotating credentials.
    component_password() {
        local path=$1
        mkdir -p "$(dirname "$path")"
        chmod 700 "$(dirname "$path")"
        if [[ -e $path ]]; then
            [[ -s $path ]] || { echo "ERROR: empty existing password file: $path" >&2; exit 1; }
        else
            openssl rand -hex 24 > "$path"
        fi
    }
    case "$component" in
        platform)
            issue_component identity platform/generated-certificates/identity ''
            issue_component web platform/generated-certificates/web "$(printf 'extendedKeyUsage=serverAuth\nsubjectAltName=DNS:%s,DNS:localhost,IP:127.0.0.1' "$hostname")"
            for entry in users/alice-password users/bob-password; do
                component_password "platform/generated-certificates/$entry"
            done
            mkdir -p platform/generated-certificates/app
            chmod 700 platform/generated-certificates/app
            ;;
        app1|app2)
            issue_component todo-client "$component/generated-certificates/todo" 'extendedKeyUsage=clientAuth'
            if [[ ! -e $component/generated-certificates/todo/ca.crt ]]; then
                cp PKI/private/ca.crt "$component/generated-certificates/todo/ca.crt"
            fi
            ;;
        help) ;;
    esac
    printf 'Component %s credentials ready; existing keys and passwords preserved.\n' "$component"
    exit 0
fi
hostname=${1:-myproduct-proxy}
if [[ $# -gt 1 || ! $hostname =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]]; then
    echo 'Usage: scripts/generate-certificates.sh [--root DIR] [DNS hostname]' >&2
    exit 2
fi
mkdir -p "$root"
cd "$root"
if [[ -e PKI/private/ca.key || -e generated-certificates/identity/identity.key ]]; then
    echo 'PKI already exists. Keeping existing keys; see PKI/README.md.' >&2
    exit 1
fi
mkdir -p PKI/private generated-certificates/{identity,todo,web,users,client}
openssl req -x509 -newkey rsa:3072 -nodes -sha256 -days 3650 \
    -keyout PKI/private/ca.key -out PKI/private/ca.crt \
    -subj '/CN=MyProduct Development CA' \
    -addext 'basicConstraints=critical,CA:TRUE' -addext 'keyUsage=critical,keyCertSign,cRLSign'
# Issue a private key and a certificate signed by the demo CA.
issue() {
    local name=$1 dir=$2 usage=$3
    openssl req -new -newkey rsa:2048 -nodes -sha256 \
        -keyout "$dir/$name.key" -out "PKI/private/$name.csr" -subj "/CN=$name"
    printf 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n%s\n' "$usage" > "PKI/private/$name.ext"
    openssl x509 -req -in "PKI/private/$name.csr" -CA PKI/private/ca.crt \
        -CAkey PKI/private/ca.key -CAcreateserial -days 365 -sha256 \
        -extfile "PKI/private/$name.ext" -out "$dir/$name.crt"
}
issue identity generated-certificates/identity ''
issue todo-client generated-certificates/todo 'extendedKeyUsage=clientAuth'
issue web generated-certificates/web "$(printf 'extendedKeyUsage=serverAuth\nsubjectAltName=DNS:%s,DNS:localhost,IP:127.0.0.1' "$hostname")"
cp generated-certificates/todo/todo-client.crt generated-certificates/client/
cp PKI/private/ca.crt generated-certificates/todo/ca.crt
openssl rand -hex 32 > generated-certificates/todo/session-key
for path in users/alice-password users/bob-password; do
    openssl rand -hex 24 > "generated-certificates/$path"
done
printf 'PKI created for %s. CA: PKI/private/ca.crt\n' "$hostname"
printf 'Demo passwords: generated-certificates/users/{alice,bob}-password\n'
