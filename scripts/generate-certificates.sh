#!/usr/bin/env bash
# Generer demo-CA, sertifikater og passord uten å erstatte eksisterende nøkler.
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
mkdir -p PKI/private generated-certificates/{identity,todo,web,identity-db,todo-db,users,client}
openssl req -x509 -newkey rsa:3072 -nodes -sha256 -days 3650 \
    -keyout PKI/private/ca.key -out PKI/private/ca.crt \
    -subj '/CN=MyProduct Development CA' \
    -addext 'basicConstraints=critical,CA:TRUE' -addext 'keyUsage=critical,keyCertSign,cRLSign'
# Utsted en privat nøkkel og et sertifikat signert av demo-CA-en.
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
for path in identity-db/password todo-db/password users/alice-password users/bob-password; do
    openssl rand -hex 24 > "generated-certificates/$path"
done
printf 'PKI created for %s. CA: PKI/private/ca.crt\n' "$hostname"
printf 'Demo passwords: generated-certificates/users/{alice,bob}-password\n'
