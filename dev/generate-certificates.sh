#!/usr/bin/env bash
# Explicit signing provisioning and retained demo recipes. No automatic deploy action.
# Self-contained for bash -s on offline targets; see docs/PFX-CREDENTIALS.md.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
umask 077
ca_subject='/CN=Demo Development CA'
ca_days=3650
cert_days=365
ca_subject_explicit=no
ca_days_explicit=no
usage() {
    echo 'Usage: generate-certificates.sh [--root DIR] [--ca-subject /CN=Name] [--ca-days N] [--cert-days N] platform|identity|app1|app2|app3|help [host]' >&2
    echo '   or: generate-certificates.sh [options] --component ID --purpose signing --pfx' >&2
    exit 2
}
while [[ $# -gt 0 ]]; do
    case "$1" in
        --root|--ca-subject|--ca-days|--cert-days)
            [[ $# -ge 2 && -n $2 ]] || usage
            case "$1" in
                --root) root=$2;;
                --ca-subject) ca_subject=$2; ca_subject_explicit=yes;;
                --ca-days) ca_days=$2; ca_days_explicit=yes;;
                --cert-days) cert_days=$2;;
            esac
            shift 2;;
        *) break;;
    esac
done
certificate_tool() {
    python3 - "$1" "$root" "$2" "$ca_subject" "$ca_days" "$cert_days" "$ca_subject_explicit" "$ca_days_explicit" <<'CERTIFICATE_TOOL'
"""Explicit credential provisioning only; never imported by deploy/validate."""

import datetime
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


def incomplete_pair(label):
    refuse(
        "Incomplete " + label + "; restore the missing file from backup. "
        "If confirmed unused after interrupted first issuance, remove only the "
        "orphan file and retry; never remove an in-use key or CA."
    )


def check_retained_ca_subject(ca_cert):
    """Compare ordered DN fields without comma/Unicode escaping ambiguities."""
    if explicit_subject != "yes":
        return
    output = openssl(
        "x509",
        "-in",
        ca_cert,
        "-noout",
        "-subject",
        "-nameopt",
        "sep_multiline,utf8,-esc_msb,sname",
    ).decode("utf-8")
    actual = [line.strip().split("=", 1) for line in output.splitlines()[1:]]
    expected = [
        list(field)
        for field in re.findall(r"/([A-Za-z][A-Za-z0-9]*)=([^/]+)", ca_subject)
    ]
    if actual != expected:
        refuse(
            "Explicit --ca-subject differs from the existing CA; retained it. "
            "Use its subject, omit the option to reuse it, or choose a separate --root."
        )


def ensure_ca():
    """One CA issuance/reuse path for full, component and signing provisioning."""
    ca = root / "PKI/private"
    plain_path(ca)
    ca_cert, ca_key = ca / "ca.crt", ca / "ca.key"
    has_ca_cert = file_exists(ca_cert)
    has_ca_key = file_exists(ca_key, private=True)
    if has_ca_cert != has_ca_key:
        incomplete_pair("existing CA")
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
            str(ca_days),
            "-keyout",
            new_key,
            "-out",
            new_cert,
            "-utf8",
            "-subj",
            ca_subject,
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
        )
        check_pair(new_cert, new_key)
        publish(new_key, ca_key)
        publish(new_cert, ca_cert)
    check_pair(ca_cert, ca_key)
    check_retained_ca_subject(ca_cert)
    return ca_cert, ca_key


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
        incomplete_pair("signing PEM pair")
    if not has_cert:
        ca_cert, ca_key = ensure_ca()
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
            str(cert_days),
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


def options(subject, ca_lifetime, leaf_lifetime):
    """Validate a documented DN subset and representable lifetimes before writes."""
    fields = re.findall(r"/([A-Za-z][A-Za-z0-9]*)=([^/]+)", subject)
    if (
        not fields
        or "".join("/" + key + "=" + value for key, value in fields) != subject
    ):
        refuse("CA subject must use /ATTRIBUTE=value fields")
    limits = {
        "CN": 64,
        "C": 2,
        "ST": 128,
        "L": 128,
        "O": 64,
        "OU": 64,
        "emailAddress": 128,
        "serialNumber": 64,
        "DC": 63,
        "UID": 64,
    }
    for key, value in fields:
        if (
            key not in limits
            or not value.strip()
            or value != value.strip()
            or len(value.encode("utf-8")) > limits.get(key, 0)
            or any(ord(c) < 32 or ord(c) == 127 or c in "\\+" for c in value)
            or (key == "C" and not re.fullmatch("[A-Z]{2}", value))
        ):
            refuse("Invalid CA subject attribute or value")
    days = []
    for name, value in (("CA days", ca_lifetime), ("Certificate days", leaf_lifetime)):
        if not re.fullmatch(r"[1-9][0-9]{0,6}", value):
            refuse(name + " must be a positive integer")
        number = int(value)
        try:
            _ = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
                days=number
            )
        except OverflowError:
            refuse(name + " exceeds the supported date range")
        days.append(number)
    return subject, days[0], days[1]


def interrupted(_signum, _frame):
    raise ProvisionError(
        "Signing provisioning interrupted; existing credentials retained"
    )


signal.signal(signal.SIGTERM, interrupted)

try:
    (
        mode,
        root_arg,
        component,
        subject,
        ca_lifetime,
        leaf_lifetime,
        explicit_subject,
        explicit_ca_days,
    ) = sys.argv[1:]
    ca_subject, ca_days, cert_days = options(subject, ca_lifetime, leaf_lifetime)
    root = Path(os.path.abspath(root_arg))
    retained_ca = root / "PKI/private/ca.crt"
    if (explicit_subject == "yes" or explicit_ca_days == "yes") and file_exists(
        retained_ca
    ):
        check_retained_ca_subject(retained_ca)
        if explicit_ca_days == "yes" and mode != "check":
            print(
                "Existing CA retained; --ca-days applies only to newly created CAs",
                file=sys.stderr,
            )
    if mode == "check":
        sys.exit(0)
    if mode == "ca":
        ca = root / "PKI/private"
        plain_path(ca)
        ca.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".ca-", dir=str(ca)) as directory:
            work = Path(directory)
            ensure_ca()
        sys.exit(0)
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
CERTIFICATE_TOOL
}
# Public option validation precedes every directory/key/certificate write.
certificate_tool check ''
# Legacy recipes cd into root before invoking the shared CA helper.
[[ $root == /* ]] || root=$PWD/$root
if [[ ${1:-} == --component ]]; then
    [[ $# == 5 && ${3:-} == --purpose && ${4:-} == signing && ${5:-} == --pfx ]] || usage
    certificate_tool signing "$2"
    exit 0
fi
if [[ ${1:-} == platform || ${1:-} == identity || ${1:-} == app1 || ${1:-} == app2 || ${1:-} == app3 || ${1:-} == help ]]; then
    component=$1
    shift
    hostname=${1:-myproduct-proxy}
    [[ $# -le 1 && $hostname =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]] || {
        echo 'Usage: generate-certificates.sh [--root DIR] platform|identity|app1|app2|app3|help [DNS hostname]' >&2; exit 2;
    }
    mkdir -p "$root/PKI/private" "$root/$component/credentials"
    chmod 700 "$root/PKI" "$root/PKI/private" "$root/$component" "$root/$component/credentials"
    cd "$root"
    certificate_tool ca ''
    # Issue missing pairs once; a partial existing pair requires operator investigation.
    issue_component() {
        local name=$1 dir=$2 usage=$3 record="PKI/private/$component-$1"
        mkdir -p "$dir"
        chmod 700 "$dir"
        if [[ -e $dir/$name.key || -e $dir/$name.crt ]]; then
            [[ -s $dir/$name.key && -s $dir/$name.crt ]] || {
                echo "ERROR: incomplete existing certificate pair: $dir/$name; restore the missing file from backup, or remove only a confirmed unused orphan from interrupted first issuance and retry; never remove an in-use key" >&2; exit 1;
            }
            return
        fi
        openssl req -new -newkey rsa:2048 -nodes -sha256 \
            -keyout "$dir/$name.key" -out "$record.csr" -subj "/CN=$component-$name"
        printf 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n%s\n' "$usage" > "$record.ext"
        openssl x509 -req -in "$record.csr" -CA PKI/private/ca.crt -CAkey PKI/private/ca.key \
            -CAcreateserial -days "$cert_days" -sha256 -extfile "$record.ext" -out "$dir/$name.crt"
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
            # A retained certificate for an earlier PUBLIC_ORIGIN would fail hostname
            # checks later in browsers and backends (backlog 76); say so now.
            web=platform/credentials/web/web.crt
            if [[ -s $web ]] && ! openssl x509 -in "$web" -noout -checkhost "$hostname" 2>/dev/null | grep -q ' does match certificate'; then
                echo "ERROR: $root/$web does not cover host name $hostname (PUBLIC_ORIGIN changed?); remove web.crt and web.key from $root/platform/credentials/web and run again to issue a new certificate from the same CA" >&2
                exit 1
            fi
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
        app3)
            issue_component client app3/credentials/client 'extendedKeyUsage=clientAuth'
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
certificate_tool ca ''
# Issue a private key and a certificate signed by the demo CA.
issue() {
    local name=$1 dir=$2 usage=$3
    openssl req -new -newkey rsa:2048 -nodes -sha256 \
        -keyout "$dir/$name.key" -out "PKI/private/$name.csr" -subj "/CN=$name"
    printf 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n%s\n' "$usage" > "PKI/private/$name.ext"
    openssl x509 -req -in "PKI/private/$name.csr" -CA PKI/private/ca.crt \
        -CAkey PKI/private/ca.key -CAcreateserial -days "$cert_days" -sha256 \
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
