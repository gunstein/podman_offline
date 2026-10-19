#!/usr/bin/env bash
# Credential provisioning: explicit signing PFX mode plus the retained demo recipes.
# See docs/PFX-CREDENTIALS.md; generation is never an automatic deploy action.
# Not part of product bundles: use external inputs or the explicit helper. On a
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
# Explicit signing provisioning is independent of demo component names. Keep the
# implementation embedded so bash -s on an offline target needs no checkout.
if [[ ${1:-} == --component ]]; then
    [[ $# == 5 && ${3:-} == --purpose && ${4:-} == signing && ${5:-} == --pfx ]] || {
        echo 'Usage: generate-certificates.sh --root DIR --component ID --purpose signing --pfx' >&2; exit 2;
    }
    exec python3 - "$root" "$2" <<'SIGNING_PFX'
"""Explicit credential provisioning only; never imported by deploy/validate."""

import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


class ProvisionError(Exception):
    pass


def refuse(message):
    raise ProvisionError(message)


def plain_path(path):
    """Reject symlinks in inputs and ancestors before opening or creating files."""
    for item in [path] + list(path.parents):
        if item.is_symlink():
            refuse("Symlinked credential path refused")


def file_exists(path, private=False):
    plain_path(path)
    if not path.exists():
        return False
    details = path.stat()
    if not stat.S_ISREG(details.st_mode) or not details.st_size:
        refuse("Credential must be a nonempty regular file")
    if private and (
        stat.S_IMODE(details.st_mode) != 0o600 or details.st_uid != os.geteuid()
    ):
        refuse("Private credential must be owned by the current user with mode 0600")
    return True


def openssl(*arguments):
    """Capture diagnostics: library errors may disclose application inputs."""
    try:
        result = subprocess.run(  # noqa: UP022 - Python 3.6
            ["openssl"] + list(map(str, arguments)),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError:
        raise ProvisionError("OpenSSL is required for signing provisioning") from None
    if result.returncode:
        refuse("OpenSSL credential operation failed; check inputs and password file")
    return result.stdout


def certificate(path):
    return openssl("x509", "-in", path, "-outform", "DER")


def public_key(path, cert=False):
    if cert:
        # A public intermediate file keeps private material out of argv/stdout.
        public = work / "certificate-public.pem"
        public.write_bytes(openssl("x509", "-in", path, "-pubkey", "-noout"))
        return openssl("pkey", "-pubin", "-in", public, "-outform", "DER")
    # PEM inputs are unencrypted; an explicit empty input prevents prompting.
    return openssl(
        "pkey", "-in", path, "-passin", "pass:", "-pubout", "-outform", "DER"
    )


def check_pair(cert, key):
    if public_key(cert, cert=True) != public_key(key):
        refuse("Certificate and private key do not match")


def verify_pfx(path, pem_cert, pem_key):
    """Require both an accessible private key and its matching leaf certificate."""
    extracted = work / "pfx-check.pem"
    openssl(
        "pkcs12",
        "-in",
        path,
        "-passin",
        "file:" + str(password),
        "-clcerts",
        "-nodes",
        "-out",
        extracted,
    )
    check_pair(extracted, extracted)
    if pem_cert and certificate(extracted) != certificate(pem_cert):
        refuse("Existing PFX and PEM certificate do not match")
    if pem_key and public_key(extracted) != public_key(pem_key):
        refuse("Existing PFX and PEM private key do not match")


def publish(source, target):
    """Hard-link publish (ln semantics): atomically refuse an existing target."""
    plain_path(target)
    try:
        os.link(str(source), str(target))
    except FileExistsError:
        refuse(
            "Credential appeared during provisioning; retained it, retry after checking"
        )


def provision():
    cert = signing / "signing-cert.crt"
    key = signing / "signing-cert.key"
    pfx = signing / "signing-cert.pfx"
    has_pfx = file_exists(pfx, private=True)
    has_cert = file_exists(cert)
    has_key = file_exists(key, private=True)
    if has_pfx:
        verify_pfx(pfx, cert if has_cert else None, key if has_key else None)
        return  # External/retained PFX wins; no CA or PEM generation.
    if has_cert != has_key:
        refuse("Incomplete signing PEM pair; restore the missing file")
    if not has_cert:
        ca = root / "PKI/private"
        plain_path(ca)
        ca_cert, ca_key = ca / "ca.crt", ca / "ca.key"
        has_ca_cert = file_exists(ca_cert)
        has_ca_key = file_exists(ca_key, private=True)
        if has_ca_cert != has_ca_key:
            refuse("Incomplete existing CA; restore it instead of regenerating")
        if not has_ca_cert:
            ca.mkdir(mode=0o700, parents=True, exist_ok=True)
            ca.parent.chmod(0o700)
            ca.chmod(0o700)
            new_cert, new_key = work / "ca.crt", work / "ca.key"
            openssl(
                "req",
                "-x509",
                "-newkey",
                "rsa:3072",
                "-nodes",
                "-sha256",
                "-days",
                "3650",
                "-keyout",
                new_key,
                "-out",
                new_cert,
                "-subj",
                "/CN=Demo Development CA",
                "-addext",
                "basicConstraints=critical,CA:TRUE",
                "-addext",
                "keyUsage=critical,keyCertSign,cRLSign",
            )
            check_pair(new_cert, new_key)
            publish(new_key, ca_key)
            publish(new_cert, ca_cert)
        check_pair(ca_cert, ca_key)
        new_key, new_cert, csr = (
            work / "signing.key",
            work / "signing.crt",
            work / "signing.csr",
        )
        openssl(
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-sha256",
            "-keyout",
            new_key,
            "-out",
            csr,
            "-subj",
            "/CN=" + component + "-signing",
        )
        extensions = work / "signing.ext"
        extensions.write_text(
            "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n"
        )
        openssl(
            "x509",
            "-req",
            "-in",
            csr,
            "-CA",
            ca_cert,
            "-CAkey",
            ca_key,
            "-passin",
            "pass:",
            "-set_serial",
            "0x" + os.urandom(16).hex(),
            "-days",
            "365",
            "-sha256",
            "-extfile",
            extensions,
            "-out",
            new_cert,
        )
        check_pair(new_cert, new_key)
        publish(new_key, key)
        publish(new_cert, cert)
    check_pair(cert, key)
    output = work / "export.pfx"
    openssl(
        "pkcs12",
        "-export",
        "-in",
        cert,
        "-inkey",
        key,
        "-passin",
        "pass:",
        "-out",
        output,
        "-passout",
        "file:" + str(password),
        "-keypbe",
        "AES-256-CBC",
        "-certpbe",
        "AES-256-CBC",
        "-macalg",
        "sha256",
    )
    verify_pfx(output, cert, key)
    publish(output, pfx)


def interrupted(_signum, _frame):
    raise ProvisionError(
        "Signing provisioning interrupted; existing credentials retained"
    )


signal.signal(signal.SIGTERM, interrupted)

try:
    root = Path(os.path.abspath(sys.argv[1]))
    component = sys.argv[2]
    if not re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?", component):
        refuse("Invalid component ID")  # Same rule as deployment.common.ID.
    signing = root / component / "credentials/signing"
    plain_path(signing)
    password = signing / "pfx-password"
    if not file_exists(password, private=True):
        refuse(
            "Missing credentials/signing/pfx-password; provision it first with mode 0600"
        )
    data = password.read_bytes()
    value = data[:-1] if data.endswith(b"\n") else data
    if not value or len(value) > 1023 or any(c in value for c in (b"\n", b"\r", b"\0")):
        refuse("PFX password file must contain one nonempty line (up to 1023 bytes)")
    for directory in (root / component, signing.parent, signing):
        if stat.S_IMODE(directory.stat().st_mode) != 0o700:
            refuse("Component credential directories must have mode 0700")
    lock = root / ".signing-provision.lock"
    plain_path(lock)
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError:
        refuse(
            "Signing provisioning busy or interrupted; check .signing-provision.lock before retry"
        )
    try:
        with tempfile.TemporaryDirectory(prefix=".pfx-", dir=str(signing)) as directory:
            work = Path(directory)
            provision()
    finally:
        lock.rmdir()
    print("Signing PFX ready; existing credentials retained")
except (ProvisionError, OSError) as error:
    # OSError text may contain sensitive names. Only our fixed messages are safe.
    print(
        "ERROR: "
        + (
            str(error)
            if isinstance(error, ProvisionError)
            else "Signing credential I/O failed"
        ),
        file=sys.stderr,
    )
    sys.exit(1)
SIGNING_PFX
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
