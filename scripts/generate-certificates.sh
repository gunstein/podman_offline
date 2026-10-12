#!/usr/bin/env bash
# Development CA and separate TLS, IdentityServer signing and Todo client keys.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
hostname=${1:-myproduct-proxy}
if [[ ! $hostname =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]]; then
    echo 'Usage: PKI/generate.sh [DNS hostname]' >&2; exit 2
fi
if [[ -e PKI/private/ca.key || -e generated-certificates/identity/identity.key ]]; then
    echo 'PKI already exists. Keeping existing keys; see PKI/README.md.' >&2
    exit 1
fi
mkdir -p PKI/private generated-certificates/{identity,todo,web,identity-db,todo-db,users,client}
openssl req -x509 -newkey rsa:3072 -nodes -sha256 -days 3650 \
    -keyout PKI/private/ca.key -out PKI/private/ca.crt \
    -subj '/CN=MyProduct Development CA' \
    -addext 'basicConstraints=critical,CA:TRUE' -addext 'keyUsage=critical,keyCertSign,cRLSign'
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
