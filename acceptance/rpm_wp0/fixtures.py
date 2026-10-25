"""Build WP0-only RPMs in the disposable OL9 container; never product code."""

import hashlib
import os
import shutil
import struct
import subprocess
from pathlib import Path

from contracts import APPROVED_FINGERPRINT, authorize_key

OUT = Path("/out")
TOP = Path("/tmp/wp0-rpmbuild")
SUPPORT = Path("/support")


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError("Fixture command failed: " + args[0])
    return result.stdout


def export(key, name):
    (OUT / name).write_text(run(["gpg", "--batch", "--armor", "--export", key]))


def sign(path, key):
    run(["rpm", "--define", "_gpg_name " + key + "!", "--addsign", str(path)])


def build(name, version, payload, guard, requires="", owned_directories=()):
    staging = TOP / (name + "-" + version)
    for path, (data, mode) in payload.items():
        target = staging / path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(mode)
    spec = TOP / (name + "-" + version + ".spec")
    spec.write_text(
        f"""%global debug_package %{{nil}}
%global __os_install_post %{{nil}}
%global _build_id_links none
Name: {name}
Version: {version}
Release: 1
Summary: WP0 fixture, not product code
License: none
BuildArch: noarch
AutoReqProv: no
{requires}
%description
Disposable WP0 investigation fixture.
%install
mkdir -p %{{buildroot}}
cp -a {staging}/. %{{buildroot}}/
%preun
{guard}
%files
%defattr(-,root,root,-)
"""
        # RPM removes only owned directories. Own each release's leaf, never
        # the shared releases parent or a sibling's tree.
        + "\n".join("%dir " + path for path in sorted(owned_directories))
        + "\n"
        + "\n".join(sorted(payload))
        + "\n"
    )
    run(["rpmbuild", "-bb", "--quiet", "--define", "_topdir " + str(TOP), str(spec)])
    target = OUT / f"{name}-{version}-1.noarch.rpm"
    shutil.copyfile(TOP / "RPMS/noarch" / target.name, target)
    sign(target, APPROVED_FINGERPRINT)


def signing_subkey(key):
    text = run(["gpg", "--batch", "--with-colons", "--list-keys", key])
    return text.split("\nsub:")[-1].split("\nfpr:", 1)[1].split(":")[8]


def main():
    TOP.mkdir()
    os.environ["GNUPGHOME"] = "/key"
    authorize_key(
        run(["gpg", "--batch", "--with-colons", "--list-keys", APPROVED_FINGERPRINT])
    )
    export(APPROVED_FINGERPRINT, "RPM-GPG-KEY-myproduct")
    payload = {
        "/usr/libexec/wp0/" + name: ((SUPPORT / name).read_bytes(), 0o644)
        for name in ("contracts.py", "operations.py", "mechanisms.py")
    }
    payload["/usr/libexec/wp0/probe_module.py"] = (
        b'VALUE = "WP0 trusted module"\n',
        0o644,
    )
    payload["/usr/bin/wp0-admin"] = (
        b"""#!/usr/bin/python3 -B
import sys
sys.path.insert(0, '/usr/libexec/wp0')
import mechanisms
try:
    mechanisms.main()
except (RuntimeError, OSError, ValueError) as error:
    print(str(error), file=sys.stderr)
    raise SystemExit(3)
""",
        0o755,
    )
    payload["/usr/bin/wp0-selfcheck"] = (
        b"""#!/bin/bash
exec python3 -B -c 'import sys; sys.path.insert(0,"/usr/libexec/wp0"); import probe_module; print(probe_module.VALUE)'
""",
        0o755,
    )
    payload["/usr/bin/wp0-runtime"] = (
        b"""#!/usr/bin/python3 -B
import sys
sys.path.insert(0, '/usr/libexec/wp0')
import mechanisms
sys.argv = [sys.argv[0], 'use', *sys.argv[1:]]
try:
    mechanisms.main()
except (RuntimeError, OSError, ValueError) as error:
    print(str(error), file=sys.stderr)
    raise SystemExit(3)
""",
        0o755,
    )
    for version in ("1.0", "2.0", "3.0"):
        build(
            "myproduct-tools",
            version,
            payload,
            f'python3 -B /usr/libexec/wp0/mechanisms.py guard myproduct-tools-{version}-1 tools "$1"',
        )
    for name in ("wp0-release-base", "wp0-release-sibling"):
        for version in ("1.0", "2.0"):
            base = "/var/lib/wp0-probe/releases/" + name
            files = {
                base + "/version": ((version + "\n").encode(), 0o644),
                base + "/deploy.sh": (
                    b"#!/bin/bash\necho release-code-ran >> /var/lib/wp0-probe/state/executed\n",
                    0o755,
                ),
            }
            checksums = "".join(
                hashlib.sha256(data).hexdigest() + "  " + Path(path).name + "\n"
                for path, (data, _) in files.items()
            )
            files[base + "/checksums.sha256"] = (checksums.encode(), 0o644)
            build(
                name,
                version,
                files,
                f'''if [ "$1" -gt 0 ]; then
cat {base}/version > /run/wp0-probe/upgrade-observed
fi
python3 -B /usr/libexec/wp0/mechanisms.py guard {name}-{version}-1 release "$1"''',
                "Requires: myproduct-tools\nRequires(preun): myproduct-tools",
                owned_directories=(base,),
            )
    delivered = OUT / "myproduct-tools-2.0-1.noarch.rpm"
    unsigned = OUT / "unsigned.rpm"
    shutil.copyfile(delivered, unsigned)
    run(["rpm", "--delsign", str(unsigned)])
    run(
        [
            "gpg",
            "--batch",
            "--pinentry-mode",
            "loopback",
            "--passphrase",
            "",
            "--quick-add-key",
            APPROVED_FINGERPRINT,
            "rsa2048",
            "sign",
            "never",
        ]
    )
    export(APPROVED_FINGERPRINT, "product-subkey.asc")
    shutil.copyfile(unsigned, OUT / "product-subkey.rpm")
    sign(OUT / "product-subkey.rpm", signing_subkey(APPROVED_FINGERPRINT))
    run(
        [
            "gpg",
            "--batch",
            "--pinentry-mode",
            "loopback",
            "--passphrase",
            "",
            "--quick-gen-key",
            "WP0 foreign <foreign@wp0.invalid>",
            "rsa2048",
            "sign",
            "never",
        ]
    )
    text = run(
        ["gpg", "--batch", "--with-colons", "--list-keys", "foreign@wp0.invalid"]
    )
    foreign = next(
        line.split(":")[9] for line in text.splitlines() if line.startswith("fpr:")
    )
    run(
        [
            "gpg",
            "--batch",
            "--pinentry-mode",
            "loopback",
            "--passphrase",
            "",
            "--quick-add-key",
            foreign,
            "rsa2048",
            "sign",
            "never",
        ]
    )
    export(foreign, "foreign.asc")
    for name, key in (
        ("foreign", foreign),
        ("foreign-subkey", signing_subkey(foreign)),
    ):
        shutil.copyfile(unsigned, OUT / (name + ".rpm"))
        sign(OUT / (name + ".rpm"), key)
    (OUT / "two-primary.asc").write_text(
        (OUT / "product-subkey.asc").read_text() + (OUT / "foreign.asc").read_text()
    )
    original = bytearray(delivered.read_bytes())
    count, size = struct.unpack_from(">II", original, 104)
    header = (96 + 16 + count * 16 + size + 7) & ~7
    count, size = struct.unpack_from(">II", original, header + 8)
    end = header + 16 + count * 16 + size
    for name, offset in (
        ("tampered-header", end - 20),
        ("tampered-payload", len(original) - 100),
    ):
        changed = original.copy()
        changed[offset] ^= 1
        (OUT / (name + ".rpm")).write_bytes(changed)
    repository = OUT / "repositories/product"
    repository.mkdir(parents=True)
    shutil.copyfile(delivered, repository / delivered.name)
    run(["createrepo_c", "--quiet", str(repository)])
    print("WP0 signature, repair, guard and repository fixtures built")


if __name__ == "__main__":
    main()
