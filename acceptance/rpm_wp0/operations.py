"""WP0 probe operations on OL9; not product code. Imported by stdin probes and RPM fixtures."""

import contextlib
import hashlib
import os
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

from contracts import (
    APPROVED_FINGERPRINT,
    TRUST_TIMEOUT,
    authorize_key,
    authorize_paper_key,
    bounded_poll,
    require,
    signature_ok,
)

INPUT = Path("/var/tmp/wp0-input")
PKG = Path("/root/pkg")
TOOLS = "myproduct-tools"
DELIVERED = "myproduct-tools-2.0-1.noarch.rpm"
TRANSCRIPT = []


def command(args, allowed=(0,), timeout=120, **kwargs):
    result = subprocess.run(
        list(map(str, args)),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        **kwargs,
    )
    TRANSCRIPT.append(
        {
            "argv": list(map(str, args)),
            "exit": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    )
    require(result.returncode in allowed, "Command failed: " + str(args[0]))
    return result


def dnf(*args, **kwargs):
    return command(
        ["dnf", "--disablerepo=*", "--setopt=localpkg_gpgcheck=1", "-y", *args],
        **kwargs,
    )


def key_text(path):
    # Keep GnuPG state out of the login home; no private signing key is needed.
    with tempfile.TemporaryDirectory(prefix="wp0-gpg-") as home:
        return command(
            ["gpg", "--homedir", home, "--batch", "--with-colons", "--show-keys", path]
        ).stdout


def copy_candidate(name, destination=PKG):
    require(Path(name).name == name, "Candidate name must be a basename")
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(
        destination.stat().st_uid == 0
        and stat.S_IMODE(destination.stat().st_mode) == 0o700,
        "Copy directory must be root-only",
    )
    directory = os.open(str(INPUT), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        with os.fdopen(fd, "rb") as source:
            require(
                stat.S_ISREG(os.fstat(source.fileno()).st_mode),
                "Candidate must be a regular file",
            )
            target = destination / name
            with target.open("xb") as output:
                shutil.copyfileobj(source, output)
    finally:
        os.close(directory)
    return target


def fresh_directory(path=PKG):
    if path.exists():
        require(not path.is_symlink(), "Scratch directory is a symlink")
        shutil.rmtree(str(path))
    path.mkdir(mode=0o700, parents=True)


def import_product(key, database=None):
    # Authorization always happens before database creation or any import.
    authorize_key(key_text(key), APPROVED_FINGERPRINT)
    args = ["rpmkeys"]
    if database is not None:
        require(not database.exists(), "Isolated database must be fresh")
        args += ["--dbpath", str(database)]
    command([*args, "--import", key])


def verify(path, database):
    result = command(
        [
            "rpmkeys",
            "--dbpath",
            database,
            "--define",
            "_pkgverify_level all",
            "-K",
            path,
        ],
        allowed=tuple(range(256)),
    )
    return signature_ok(result.returncode, result.stdout + result.stderr)


@contextlib.contextmanager
def paper_delivery(key_name="RPM-GPG-KEY-myproduct", package=DELIVERED):
    """Select one test delivery; old/new repair setup RPMs are not on the medium."""
    with tempfile.TemporaryDirectory(prefix="wp0-paper-delivery-") as temporary:
        delivery = Path(temporary)
        key = copy_candidate(key_name, delivery)
        key.rename(delivery / "RPM-GPG-KEY-myproduct")
        candidate = copy_candidate(package, delivery)
        # Signature variants keep their bytes; only the delivery basename changes
        # so the paper's wildcard selects the assigned candidate.
        candidate.rename(delivery / DELIVERED)
        TRANSCRIPT.append(
            {
                "paper_fixture_setup": {
                    "key_source": key_name,
                    "candidate_source": package,
                    "delivery": str(delivery),
                    "candidate_basename": DELIVERED,
                    "candidate_sha256": file_digest(delivery / DELIVERED),
                    "gpg_state": "temporary GNUPGHOME; paper gpg arguments unchanged",
                }
            }
        )
        yield delivery


def paper_command(script, **kwargs):
    # These fixed OS commands contain public paths only. Record their exact
    # shell source explicitly; arbitrary stdin and credential bytes stay private.
    TRANSCRIPT.append({"paper_command": script, "cwd": str(kwargs.get("cwd", ""))})
    return command(["bash", "-se"], input=script, **kwargs)


def paper_verify(delivery):
    """Execute the paper's OS commands, stopping between lines for its checks."""
    scratch, medium = shlex.quote(str(PKG)), shlex.quote(str(delivery))
    paper_command(
        f"""rm -rf {scratch}
mkdir -m 0700 {scratch}
cd {scratch}
cp {medium}/RPM-GPG-KEY-myproduct {medium}/myproduct-tools-*.rpm .
""",
    )
    # GnuPG state is temporary, without changing the paper command's arguments.
    with tempfile.TemporaryDirectory(prefix="wp0-paper-gpg-") as home:
        displayed = command(
            ["gpg", "--show-keys", "RPM-GPG-KEY-myproduct"],
            cwd=PKG,
            env=dict(os.environ, GNUPGHOME=home, LC_ALL="C"),
        )
    authorize_paper_key(displayed.stdout, APPROVED_FINGERPRINT)
    command(
        ["rpmkeys", "--dbpath", str(PKG / "db"), "--import", "RPM-GPG-KEY-myproduct"],
        cwd=PKG,
    )
    result = paper_command(
        f"rpmkeys --dbpath {scratch}/db --define '_pkgverify_level all' -K myproduct-tools-*.rpm\n",
        cwd=PKG,
        allowed=tuple(range(256)),
    )
    return signature_ok(result.returncode, result.stdout + result.stderr)


def verify_paper_delivery(key_name="RPM-GPG-KEY-myproduct", package=DELIVERED):
    with paper_delivery(key_name, package) as delivery:
        return paper_verify(delivery)


def paper_install(action):
    require(action in ("install", "reinstall"), "Unknown paper repair action")
    command(["rpm", "--import", "RPM-GPG-KEY-myproduct"], cwd=PKG)
    paper_command(
        "dnf --disablerepo='*' --setopt=localpkg_gpgcheck=1 -y "
        + action
        + " ./myproduct-tools-*.rpm\n",
        cwd=PKG,
    )
    return True


def bootstrap(key_name="RPM-GPG-KEY-myproduct", package=DELIVERED, action="install"):
    require(
        verify_paper_delivery(key_name, package),
        "STOP: package signature or digests differ from paper",
    )
    return paper_install(action)


def install_verified(names):
    fresh_directory()
    key = copy_candidate("RPM-GPG-KEY-myproduct")
    import_product(key, PKG / "db")
    packages = [copy_candidate(name) for name in names]
    for path in packages:
        require(verify(path, PKG / "db"), "Candidate signature failed")
    import_product(key)
    dnf("install", *map(str, packages))
    return True


def versions(package=TOOLS):
    result = command(["rpm", "-q", package, "--qf", "%{VERSION}\\n"], allowed=(0, 1))
    if result.returncode == 1:
        require(
            result.stdout.strip() == "package " + package + " is not installed"
            and not result.stderr.strip(),
            "RPM package query failed ambiguously",
        )
        return []
    return sorted(result.stdout.splitlines())


def rpm_clean(package):
    result = command(["rpm", "-V", package], allowed=tuple(range(256)))
    return (
        result.returncode == 0
        and not result.stdout.strip()
        and not result.stderr.strip()
    )


def trust_inventory(packages, code_only=False):
    inventory = {}
    for package in packages:
        output = command(
            [
                "rpm",
                "-q",
                "--qf",
                "[%{FILENAMES}\\t%{FILESIZES}\\t%{FILEDIGESTS}\\t%{FILEMODES}\\n]",
                package,
            ]
        ).stdout
        for line in output.splitlines():
            path, size, digest, mode = line.split("\t")
            if not stat.S_ISREG(int(mode)):
                continue
            if code_only and "/releases/" in path and "/deployment/" not in path:
                continue
            require(len(digest) == 64, "RPM inventory must use SHA256")
            inventory[path] = (int(size), digest)
    require(bool(inventory), "Empty trust inventory")
    return inventory


def trust_matches(output, inventory):
    rows = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 4:
            continue
        source, path, size, digest = fields
        if path in inventory:
            if source != "rpmdb" or not size.isdigit():
                return False
            if (int(size), digest) != inventory[path]:
                return False
            rows[path] = (int(size), digest)
        # A file-trust record elsewhere in a release is also forbidden.
        if "/var/lib/myproduct/releases/" in path and source != "rpmdb":
            return False
    return rows == inventory


def wait_trust(packages, code_only=False):
    inventory = trust_inventory(packages, code_only)

    def poll(remaining):
        result = command(["fapolicyd-cli", "--dump-db"], timeout=remaining)
        return trust_matches(result.stdout, inventory)

    return bounded_poll(poll, TRUST_TIMEOUT)


def global_keys():
    # Compare complete public certificates, not RPM's short key identifiers.
    output = command(["rpm", "-qa", "gpg-pubkey", "--qf", "%{DESCRIPTION}\\n"]).stdout
    blocks = re.findall(
        r"-----BEGIN PGP PUBLIC KEY BLOCK-----.*?-----END PGP PUBLIC KEY BLOCK-----",
        output,
        re.DOTALL,
    )
    rest = output
    for block in blocks:
        rest = rest.replace(block, "", 1)
    require(not rest.strip(), "Cannot inventory global RPM public certificates")
    return sorted(blocks)


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
