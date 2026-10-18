#!/usr/bin/env bash
# Demo provisioning: generate the demo CA, certificates and passwords without replacing existing keys.
# Not part of product bundles: an organisation brings its own certificates. On a
# target, pass it on stdin: bash -s -- --root DIR <component> <host> < generate-certificates.sh
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
umask 077
if [[ ${1:-} == --root ]]; then
    if [[ $# -lt 2 || -z $2 ]]; then
        echo 'Usage: dev/generate-certificates.sh [--root DIR] [DNS hostname]' >&2
        exit 2
    fi
    root=$2
    shift 2
fi
if [[ ${1:-} == platform || ${1:-} == identity || ${1:-} == app1 || ${1:-} == app2 || ${1:-} == help ]]; then
    component=$1
    shift
    hostname=${1:-myproduct-proxy}
    [[ $# -le 1 && $hostname =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]] || {
        echo 'Usage: generate-certificates.sh [--root DIR] platform|identity|app1|app2|help [DNS hostname]' >&2; exit 2;
    }
    mkdir -p "$root/PKI/private" "$root/$component/credentials"
    chmod 700 "$root/PKI" "$root/PKI/private" "$root/$component" "$root/$component/credentials"
    cd "$root"
    if [[ -e PKI/private/ca.key || -e PKI/private/ca.crt ]]; then
        [[ -s PKI/private/ca.key && -s PKI/private/ca.crt ]] || {
            echo 'ERROR: incomplete existing CA; do not regenerate it' >&2; exit 1;
        }
    else
        openssl req -x509 -newkey rsa:3072 -nodes -sha256 -days 3650 \
            -keyout PKI/private/ca.key -out PKI/private/ca.crt \
            -subj '/CN=Demo Development CA' \
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
            issue_component web platform/credentials/web "$(printf 'extendedKeyUsage=serverAuth\nsubjectAltName=DNS:%s,DNS:localhost,IP:127.0.0.1' "$hostname")"
            ;;
        identity)
            issue_component identity identity/credentials/identity ''
            for entry in users/alice-password users/bob-password; do
                component_password "identity/credentials/$entry"
            done
            ;;
        app1|app2)
            issue_component todo-client "$component/credentials/todo" 'extendedKeyUsage=clientAuth'
            if [[ ! -e $component/credentials/todo/ca.crt ]]; then
                cp PKI/private/ca.crt "$component/credentials/todo/ca.crt"
            fi
            ;;
        help) ;;
    esac
    printf 'Component %s credentials ready; existing keys and passwords preserved.\n' "$component"
    exit 0
fi
hostname=${1:-myproduct-proxy}
if [[ $# -gt 1 || ! $hostname =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]]; then
    echo 'Usage: dev/generate-certificates.sh [--root DIR] [DNS hostname]' >&2
    exit 2
fi
mkdir -p "$root"
cd "$root"
if [[ -e PKI/private/ca.key || -e credentials/identity/identity.key ]]; then
    echo 'PKI already exists. Keeping existing keys; see PKI/README.md.' >&2
    exit 1
fi
mkdir -p PKI/private credentials/{identity,todo,web,users,client}
openssl req -x509 -newkey rsa:3072 -nodes -sha256 -days 3650 \
    -keyout PKI/private/ca.key -out PKI/private/ca.crt \
    -subj '/CN=Demo Development CA' \
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
issue identity credentials/identity ''
issue todo-client credentials/todo 'extendedKeyUsage=clientAuth'
issue web credentials/web "$(printf 'extendedKeyUsage=serverAuth\nsubjectAltName=DNS:%s,DNS:localhost,IP:127.0.0.1' "$hostname")"
cp credentials/todo/todo-client.crt credentials/client/
cp PKI/private/ca.crt credentials/todo/ca.crt
openssl rand -hex 32 > credentials/todo/session-key
for path in users/alice-password users/bob-password; do
    openssl rand -hex 24 > "credentials/$path"
done
printf 'PKI created for %s. CA: PKI/private/ca.crt\n' "$hostname"
printf 'Demo passwords: credentials/users/{alice,bob}-password\n'
