"""Privileged offline release publication. Run authenticated code via stdin, Python 3.6.

Never import code from an incoming archive. /var/lib/<product> (the root-owned
installation root, backlog 64) and the independent keyring are root controlled;
releases/ beneath it is root-only. The account's state/, config/ and storage/
siblings are never opened by release publication; setup delegates their creation
to the authenticated host script with its existing privilege drop.
"""
# ruff: noqa: UP021, UP022
# Host Python 3.6 requires PIPE/universal_newlines, not capture_output/text.

import argparse
import errno
import fcntl
import hashlib
import json
import os
import pwd
import re
import shlex
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
from contextlib import contextmanager, suppress
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit(
        "ERROR: release tool requires python3-pyyaml; administrator must install "
        "that OL9 package from the approved offline repository, then repeat setup"
    ) from None

BASE = Path("/var/lib")
OWNER = 0
TRUST_DIR = Path("/etc/fapolicyd/trust.d")
RECORD = ".release.json"
ID = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
PRODUCT = re.compile(r"^[a-z]([a-z0-9-]{0,30}[a-z0-9])?$")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
PART = re.compile(r"^[A-Za-z0-9_+@.-]+$")


class ReleaseError(Exception):
    pass


class CommandError(ReleaseError):
    def __init__(self, executable, returncode):
        self.executable = executable
        self.returncode = returncode
        super().__init__("command failed: " + executable + " exit=" + str(returncode))


def require(condition, message):
    if not condition:
        raise ReleaseError(message)


def error_message(error):
    """Report our fixed messages, never external stderr, config or file contents."""
    if isinstance(error, ReleaseError):
        return str(error)
    if isinstance(error, OSError):
        return "OS error errno=" + str(error.errno)
    if isinstance(error, KeyError):
        return "missing provenance field"
    return type(error).__name__


@contextmanager
def diagnostic(step, path=None):
    # Paths here refer to public release metadata, never credential sources.
    label = step
    if path is not None:
        value = str(path)
        label += (
            " ["
            + (value if re.fullmatch(r"[A-Za-z0-9_+@./-]+", value) else "invalid path")
            + "]"
        )
    try:
        yield
    except (
        ReleaseError,
        OSError,
        ValueError,
        KeyError,
        tarfile.TarError,
        subprocess.TimeoutExpired,
        yaml.YAMLError,
    ) as error:
        raise ReleaseError(label + ": " + error_message(error)) from None


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def protected(path, directory=False):
    with diagnostic("check protected object", path):
        check_protected(path, directory)


def check_protected(path, directory=False):
    """Refuse links, aliases, ACL grants, foreign owners and writable permissions."""
    info = path.lstat()
    require(
        info.st_uid == OWNER and not info.st_mode & 0o022,
        "unprotected ownership or permissions",
    )
    require(
        stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode),
        "unexpected object type",
    )
    if not directory:
        require(info.st_nlink == 1, "hardlinked protected file")
    for attribute in ("system.posix_acl_access", "system.posix_acl_default"):
        try:
            os.getxattr(str(path), attribute, follow_symlinks=False)
        except OSError as error:
            if error.errno not in (errno.ENODATA, errno.ENOTSUP):
                raise
        else:
            raise ReleaseError("ACL on protected path")


def ancestors(path):
    require(path.is_absolute(), "absolute protected path required")
    require(".." not in path.parts, "unsafe protected path")
    for entry in reversed((path,) + tuple(path.parents)):
        protected(entry, directory=True)


def identity(product, component, version):
    require(
        all(isinstance(value, str) for value in (product, component, version))
        and PRODUCT.fullmatch(product)
        and ID.fullmatch(component)
        and VERSION.fullmatch(version),
        "invalid release identity",
    )
    return product + "-" + component + "-" + version


@contextmanager
def product_lock(product):
    require(PRODUCT.fullmatch(product), "invalid product")
    ancestors(BASE)
    root = BASE / product
    for path in (root, root / "releases"):
        with suppress(FileExistsError):
            path.mkdir(mode=0o755)
        protected(path, directory=True)
        require(
            stat.S_IMODE(path.stat().st_mode) == 0o755,
            "unexpected protected directory mode",
        )
    lock = root / ".release.lock"
    fd = os.open(
        str(lock), os.O_CREAT | os.O_NOFOLLOW | os.O_RDWR | os.O_NONBLOCK, 0o600
    )
    try:
        protected(lock)
        deadline = time.monotonic() + 60
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(time.monotonic() < deadline, "release lock timed out")
                time.sleep(0.1)
        yield root
    finally:
        os.close(fd)


def command(arguments, allowed=(0,)):
    result = subprocess.run(
        arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=60,
        check=False,
    )
    if result.returncode not in allowed:
        raise CommandError(arguments[0], result.returncode)
    return result


def copy_input(source, target):
    """Snapshot a regular input; its parents may be operator/service controlled."""
    with diagnostic("snapshot input", target.name):
        fd = os.open(str(source), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            require(
                stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "input is not regular"
            )
            with target.open("xb") as output:
                shutil.copyfileobj(stream, output)


def safe_name(name):
    parts = name.split("/")
    require(
        all(part not in ("", ".", "..") and PART.fullmatch(part) for part in parts),
        "unsafe archive name",
    )
    return parts


def archive_members(archive, name):
    """One archive-shape validator for extraction and authenticated sizing."""
    members = archive.getmembers()
    seen = set()
    for member in members:
        parts = safe_name(member.name)
        require(
            parts[0] == name and member.name not in seen,
            "wrong archive root or duplicate member",
        )
        require(
            member.type in (tarfile.DIRTYPE, tarfile.REGTYPE, tarfile.AREGTYPE)
            and not member.issparse(),
            "archive link, sparse or special file",
        )
        require(
            not member.mode & 0o7022
            and not member.pax_headers.keys()
            - {"mtime", "atime", "ctime", "path", "size"},
            "unsafe archive metadata",
        )
        require(member.name != name + "/" + RECORD, "reserved archive name")
        seen.add(member.name)
    require(name in seen, "missing archive root")
    # Explicit parents prevent a file/directory alias regardless of tar order.
    for member in members:
        for parent in Path(member.name).parents:
            if str(parent) == ".":
                break
            require(
                str(parent) in seen
                and any(item.name == str(parent) and item.isdir() for item in members),
                "missing or non-directory parent",
            )
    return members


def extract(
    snapshot, destination, name, product, component, version, setup_space=False
):
    """Validate all members, then copy bytes; tar never creates links or metadata."""
    with tarfile.open(str(snapshot), "r:gz") as archive:
        members = archive_members(archive, name)
        if setup_space:
            extraction_space(destination, members, name)
        hashes, metadata = {}, {}
        for member in sorted(
            members, key=lambda item: (len(Path(item.name).parts), item.name)
        ):
            path = destination / member.name
            if member.isdir():
                path.mkdir(mode=0o755)
            else:
                source = archive.extractfile(member)
                if source is None:
                    raise ReleaseError("missing archive file stream")
                relative = str(Path(member.name).relative_to(name))
                value = hashlib.sha256()
                chunks = []
                is_metadata = relative in ("VERSION", "bundle.yaml", "checksums.sha256")
                if is_metadata:
                    require(
                        member.size <= 16 * 1024 * 1024, "oversized release metadata"
                    )
                with source, path.open("xb") as output:
                    for block in iter(
                        lambda source=source: source.read(1024 * 1024), b""
                    ):
                        output.write(block)
                        value.update(block)
                        if is_metadata:
                            chunks.append(block)
                    output.flush()
                    os.fchmod(output.fileno(), 0o755 if member.mode & 0o111 else 0o644)
                    os.fsync(output.fileno())
                hashes[relative] = value.hexdigest()
                if is_metadata:
                    metadata[relative] = b"".join(chunks).decode("utf-8")
    tree = destination / name
    require(metadata.get("VERSION", "").strip() == version, "VERSION mismatch")
    descriptor = yaml.safe_load(metadata.get("bundle.yaml", ""))
    require(
        isinstance(descriptor, dict)
        and (
            descriptor.get("product"),
            descriptor.get("name"),
            descriptor.get("version"),
        )
        == (product, component, version),
        "descriptor identity mismatch",
    )
    files, directories, bindings = inventory(tree, hashes)
    checksums = {}
    for line in metadata.get("checksums.sha256", "").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            raise ReleaseError("invalid checksum record")
        key = match.group(2)
        safe_name(key)
        require(key not in checksums, "duplicate checksum record")
        checksums[key] = match.group(1)
    require(
        checksums
        == {
            key: value["sha256"]
            for key, value in files.items()
            if key != "checksums.sha256"
        },
        "checksum inventory mismatch",
    )
    require(
        any(key.startswith("deployment/") for key in files), "empty deployment package"
    )
    return tree, files, directories, bindings


def inventory(tree, hashes):
    """Bind streamed authenticated hashes to unchanged protected filesystem objects.

    Do not reopen payload files here: the default fapolicyd language policy can
    deny even root reading untrusted Python before enrollment. Hashes come from
    the verified archive stream while writing, and protected inode/mtime bindings
    refuse ordinary payload changes (including same-size writes) before or after publication.
    ctime is deliberately excluded: SELinux relabeling updates it without changing
    payloads. Root and its relabel tools are trusted; service users cannot write.
    """
    protected(tree, directory=True)
    require(
        stat.S_IMODE(tree.stat().st_mode) == 0o755, "unexpected release directory mode"
    )
    files, directories, bindings = {}, [], {}
    for directory, dirs, names in os.walk(str(tree), followlinks=False):
        for name in sorted(dirs + names):
            path = Path(directory) / name
            if path == tree / RECORD:
                protected(path)
                continue
            relative = str(path.relative_to(tree))
            info = path.lstat()
            is_directory = stat.S_ISDIR(info.st_mode)
            protected(path, directory=is_directory)
            mode = stat.S_IMODE(info.st_mode)
            require(
                mode in ((0o755,) if is_directory else (0o644, 0o755)),
                "unexpected published mode",
            )
            bindings[relative] = [
                info.st_dev,
                info.st_ino,
                info.st_mtime_ns,
            ]
            if is_directory:
                directories.append(relative)
            else:
                files[relative] = {
                    "size": info.st_size,
                    "sha256": hashes.get(relative),
                    "mode": mode,
                }
    require(set(files) == set(hashes), "published file set changed")
    return files, sorted(directories), bindings


def published(path):
    with diagnostic("validate published inventory", path):
        return read_published(path)


def read_published(path):
    ancestors(path.parent)
    protected(path, directory=True)
    protected(path / RECORD)
    record = json.loads((path / RECORD).read_text())
    require(
        record["name"] == path.name
        and identity(record["product"], record["component"], record["version"])
        == path.name,
        "provenance identity mismatch",
    )
    files, directories, bindings = inventory(
        path, {key: value["sha256"] for key, value in record["files"].items()}
    )
    require(
        record["files"] == files
        and record["directories"] == directories
        and record["bindings"] == bindings,
        "published inventory changed",
    )
    return record


def publish(root, archive, signature, product, component, version, setup_space=False):
    name = identity(product, component, version)
    keyring = root / "keyring.gpg"
    ancestors(keyring.parent)
    protected(keyring)
    final = root / "releases" / name
    # Keep image-sized staging under /var/lib, not /run's small tmpfs. Lock serializes
    # publication and trust for this product; root is the only writer here.
    with tempfile.TemporaryDirectory(prefix=".staging-", dir=str(root)) as directory:
        stage = Path(directory)
        snapshot, sig = stage / "archive", stage / "signature"
        print("START: protected release snapshot/authentication", flush=True)
        if setup_space:
            check_space([(root, regular_size(archive))])
        copy_input(archive, snapshot)
        copy_input(signature, sig)
        (stage / "gnupg").mkdir(mode=0o700)
        command(
            [
                "gpgv",
                "--homedir",
                str(stage / "gnupg"),
                "--keyring",
                str(keyring),
                str(sig),
                str(snapshot),
            ]
        )
        print("PASS: archive signature; START: validated extraction", flush=True)
        with diagnostic("validate/extract signed archive", name):
            tree, files, directories, bindings = extract(
                snapshot,
                stage,
                name,
                product,
                component,
                version,
                setup_space=setup_space,
            )
        record = {
            "name": name,
            "product": product,
            "component": component,
            "version": version,
            "archive_sha256": digest(snapshot),
            "files": files,
            "directories": directories,
            "bindings": bindings,
        }
        (tree / RECORD).write_text(json.dumps(record, sort_keys=True) + "\n")
        (tree / RECORD).chmod(0o644)
        with (tree / RECORD).open("rb") as stream:
            os.fsync(stream.fileno())
        for directory in sorted(
            [tree] + [tree / name for name in directories],
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            sync_directory(directory)
        if os.path.lexists(str(final)):
            previous = published(final)
            require(
                {key: value for key, value in previous.items() if key != "bindings"}
                == {key: value for key, value in record.items() if key != "bindings"},
                "immutable release version conflict",
            )
        else:
            # rename is atomic on this filesystem. The held lock and protected
            # parent prevent replacement by a concurrent service user/helper.
            os.rename(str(tree), str(final))
            sync_directory(final.parent)
    print("PASS: authenticated immutable release publication", flush=True)
    return final


def sync_directory(path):
    fd = os.open(str(path), os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def trust_records(text):
    require(text.strip(), "empty trust database")
    rows = []
    for line in text.splitlines():
        match = re.fullmatch(r"\S+ (/.+) ([0-9]+) ([0-9a-fA-F]{64})", line)
        if match is None:
            raise ReleaseError("invalid trust database record")
        rows.append((match.group(1), int(match.group(2)), match.group(3).lower()))
    return rows


def wait_trust(path, removed=None, attempts=30):
    record = published(path)
    wanted = {
        str(path / key): (value["size"], value["sha256"])
        for key, value in record["files"].items()
        if key.startswith("deployment/")
    }
    for attempt in range(attempts):
        rows = trust_records(command(["fapolicyd-cli", "--dump-db"]).stdout)
        observed = [
            (name, size, value)
            for name, size, value in rows
            if name.startswith(str(path / "deployment") + "/")
        ]
        old = removed and any(
            name.startswith(str(removed / "deployment") + "/") for name, _, _ in rows
        )
        if (
            len(observed) == len(wanted)
            and len({row[0] for row in observed}) == len(wanted)
            and {name: (size, value) for name, size, value in observed} == wanted
            and not old
        ):
            print("PASS: authenticated package trust ready", flush=True)
            return
        if attempt + 1 < attempts:
            time.sleep(1)
    raise ReleaseError("trust inventory not ready after bounded polling")


def integrity_policy():
    path = FAPOLICYD
    ancestors(path.parent)
    protected(path)
    values = re.findall(
        r"^\s*integrity\s*=\s*(\S+)\s*(?:#.*)?$", path.read_text(), re.MULTILINE
    )
    require(
        len(values) == 1 and values[0] in ("none", "size", "sha256"),
        "unsupported or ambiguous fapolicyd integrity policy",
    )
    print("INFO: protected release; fapolicyd integrity=" + values[0], flush=True)


def scoped_trust(path, remove=False):
    """Atomically manage only authenticated records in this component's trust file.

    fapolicyd's documented three-field file format avoids opening untrusted
    language files just to enroll them. Never rederive expected hashes from live
    files or invoke recursive CLI traversal. Old verified versions stay listed.
    """
    record = published(path)
    ancestors(TRUST_DIR)
    target = TRUST_DIR / (
        "podman-offline-" + record["product"] + "." + record["component"]
    )
    current = {}
    if os.path.lexists(str(target)):
        protected(target)
        for line in target.read_text().splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            match = re.fullmatch(r"(/\S+) ([0-9]+) ([0-9a-f]{64})", line)
            if match is None:
                raise ReleaseError("invalid scoped trust file")
            key, size, value = match.groups()
            require(key not in current, "duplicate scoped trust record")
            current[key] = (int(size), value)
    prefix = str(path / "deployment") + "/"
    # Refuse unrelated or unauthenticated entries even in our root-owned scope.
    verified = {}
    for key, value in current.items():
        candidate = Path(key)
        relative = candidate.relative_to(
            path.parent
        )  # confines to this product's releases
        if len(relative.parts) < 3 or relative.parts[1] != "deployment":
            raise ReleaseError("unexpected scoped trust path")
        release = path.parent / relative.parts[0]
        if release not in verified:
            previous = published(release)
            require(
                (previous["product"], previous["component"])
                == (record["product"], record["component"]),
                "foreign scoped trust record",
            )
            verified[release] = previous
        file = str(candidate.relative_to(release))
        expected = verified[release]["files"].get(file, {})
        require(
            value == (expected.get("size"), expected.get("sha256")),
            "scoped trust differs from authenticated inventory",
        )
    desired = {
        key: value for key, value in current.items() if not key.startswith(prefix)
    }
    if not remove:
        desired.update(
            {
                str(path / key): (value["size"], value["sha256"])
                for key, value in record["files"].items()
                if key.startswith("deployment/")
            }
        )
    if desired == current:
        print(
            "INFO: authenticated trust records already present/absent; verifying live state",
            flush=True,
        )
        return
    text = "# Authenticated protected releases; managed by release.py\n"
    text += "".join(
        key + " " + str(value[0]) + " " + value[1] + "\n"
        for key, value in sorted(desired.items())
    )
    # Stage outside trust.d so an asynchronous reload never sees partial input.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", prefix=".release-trust-", dir=str(TRUST_DIR.parent), delete=False
        ) as output:
            temporary = Path(output.name)
            output.write(text)
            output.flush()
            os.fchmod(output.fileno(), 0o644)
            os.fsync(output.fileno())
        os.replace(str(temporary), str(target))
        sync_directory(TRUST_DIR)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def enroll(path):
    published(path)
    integrity_policy()
    scoped_trust(path)
    command(["fapolicyd-cli", "--update"])
    wait_trust(path)


def withdraw(path):
    """Remove only this verified package's trust; retain its release files."""
    scoped_trust(path, remove=True)
    prefix = str(path / "deployment") + "/"
    command(["fapolicyd-cli", "--update"])
    for attempt in range(30):
        rows = trust_records(command(["fapolicyd-cli", "--dump-db"]).stdout)
        if not any(name.startswith(prefix) for name, _, _ in rows):
            return
        if attempt < 29:
            time.sleep(1)
    raise ReleaseError("old trust did not disappear after bounded polling")


def retire(root, path, old):
    """Journal an authenticated retirement so interrupted deletion can resume."""
    marker = root / (".retirement-" + old.name + ".json")
    trash = root / (".retired-" + old.name)
    journal = None
    if os.path.lexists(str(marker)):
        protected(marker)
        journal = json.loads(marker.read_text())
        require(
            journal["keep"] == path.name and journal["record"]["name"] == old.name,
            "retirement retry identity conflict",
        )
    require(
        not os.path.lexists(str(trash)) or journal is not None,
        "retired tree without protected provenance",
    )
    if os.path.lexists(str(old)):
        require(not os.path.lexists(str(trash)), "conflicting retirement trees")
        previous = published(old)
        require(
            journal is None or journal["record"] == previous,
            "retirement source changed",
        )
        withdraw(old)
    else:
        previous = journal["record"] if journal else None
    wait_trust(path, old)
    if previous is None:
        return
    if journal is None:
        journal = {"keep": path.name, "record": previous}
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", prefix=".retirement-stage-", dir=str(root), delete=False
            ) as output:
                temporary = Path(output.name)
                output.write(json.dumps(journal, sort_keys=True) + "\n")
                output.flush()
                os.fsync(output.fileno())
            os.rename(str(temporary), str(marker))
            sync_directory(root)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    if os.path.lexists(str(old)):
        os.rename(str(old), str(trash))
        sync_directory(old.parent)
        sync_directory(root)
    if os.path.lexists(str(trash)):
        protected(trash, directory=True)
        # Partial deletion changes directory timestamps; only remaining files
        # must retain their authenticated identity. Missing objects are expected.
        for directory, dirs, names in os.walk(str(trash), followlinks=False):
            for name in dirs + names:
                candidate = Path(directory) / name
                relative = str(candidate.relative_to(trash))
                info = candidate.lstat()
                is_directory = stat.S_ISDIR(info.st_mode)
                protected(candidate, directory=is_directory)
                if is_directory:
                    require(
                        relative in previous["directories"],
                        "unexpected retired directory",
                    )
                elif relative != RECORD:
                    expected = previous["files"].get(relative)
                    require(
                        expected is not None
                        and expected["size"] == info.st_size
                        and expected["mode"] == stat.S_IMODE(info.st_mode)
                        and previous["bindings"][relative]
                        == [
                            info.st_dev,
                            info.st_ino,
                            info.st_mtime_ns,
                        ],
                        "unexpected retired file",
                    )
        shutil.rmtree(str(trash))
        sync_directory(root)
    marker.unlink()
    sync_directory(root)


RESERVE = 1024 * 1024 * 1024
JOURNAL = Path("/var/log/journal")
TMP = Path("/var/tmp")
SYSTEMD = Path("/etc/systemd/system")
FAPOLICYD = Path("/etc/fapolicyd/fapolicyd.conf")
OS_RELEASE = Path("/etc/os-release")


def setup_request(args):
    """Validate explicit selections without touching the host or uploaded files."""
    require(PRODUCT.fullmatch(args.product), "invalid product")
    require(
        args.user and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,31}", args.user),
        "setup requires --user with an existing login account",
    )
    require(
        args.port is not None and 1024 <= args.port <= 65535,
        "setup requires --port 1024-65535",
    )
    require(
        args.input_dir is not None
        and args.input_dir.is_absolute()
        and ".." not in args.input_dir.parts,
        "setup requires an absolute --input-dir",
    )
    require(
        args.keyring is not None
        and args.keyring.is_absolute()
        and args.key_sha256
        and re.fullmatch(r"[0-9a-f]{64}", args.key_sha256),
        "setup requires --keyring and its independent --key-sha256",
    )
    require(
        not any(
            (
                args.component,
                args.version,
                args.archive,
                args.signature,
                args.old_version,
            )
        ),
        "setup uses --release, not single-release arguments",
    )
    selected, seen = [], set()
    for item in args.release:
        parts = item.split("@")
        require(len(parts) == 2, "use --release COMPONENT@VERSION")
        component, version = parts
        name = identity(args.product, component, version)
        require(
            component not in seen,
            "select one version per component, without duplicates",
        )
        seen.add(component)
        archive = args.input_dir / (name + "-offline.tar.gz")
        selected.append((component, version, archive, Path(str(archive) + ".asc")))
    require(
        selected and args.host_release in args.release,
        "--host-release must name one of the explicit --release selections",
    )
    return selected


def regular_size(path):
    """Inspect a regular input without following its final link or blocking on a FIFO."""
    with diagnostic("read selected input", path):
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            require(
                stat.S_ISREG(info.st_mode), "input must be a regular file: " + str(path)
            )
            return info.st_size
        finally:
            os.close(fd)


def input_digest(path):
    """Hash one held regular input, never reopen a path after checking its type."""
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        require(
            stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "key input is not regular"
        )
        value = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def check_space(allocations):
    """Sum simultaneous allocations on each filesystem, keeping one reserve."""
    devices = {}
    for path, size in allocations:
        require(
            not os.statvfs(str(path)).f_flag & os.ST_RDONLY,
            "read-only filesystem at "
            + str(path)
            + "; administrator must provide a writable approved filesystem before retry",
        )
        device = path.stat().st_dev
        previous = devices.get(device, (path, 0))
        devices[device] = (previous[0], previous[1] + size)
    for path, size in devices.values():
        free = shutil.disk_usage(str(path)).free
        required = size + RESERVE
        require(
            free >= required,
            "space at "
            + str(path)
            + ": required="
            + str(required)
            + " free="
            + str(free)
            + "; administrator must free space or extend this filesystem before retry",
        )


def extraction_space(destination, members, name):
    """Called only after signature verification and shared member validation."""
    size = sum(member.size for member in members if member.isfile())
    images = sum(
        member.size for member in members if member.name == name + "/images/images.tar"
    )
    check_space([(destination, size), (TMP, images), (JOURNAL.parent, 0)])


def setting_values(text):
    """Read simple fapolicyd settings; duplicates are an error, not a guessed policy."""
    result = {}
    for line in text.splitlines():
        match = re.fullmatch(r"\s*([a-z_]+)\s*=\s*(\S+)\s*(?:#.*)?", line)
        if match:
            key, value = match.groups()
            require(key not in result, "ambiguous fapolicyd setting " + key)
            result[key] = value
    return result


def journal_settings(text):
    """cat-config supplies systemd's ordered files; track section and source."""
    values = {"Storage": ("auto", "OL9 default"), "SplitMode": ("uid", "OL9 default")}
    section, source = "", "journald configuration"
    for line in text.splitlines():
        if line.startswith("# /"):
            source = line[2:]
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
        elif section == "Journal" and not line.startswith(("#", ";")) and "=" in line:
            key, value = (part.strip() for part in line.split("=", 1))
            if key in values:
                values[key] = (value, source)
    for key, allowed in (("Storage", ("auto", "persistent")), ("SplitMode", ("uid",))):
        value, source = values[key]
        require(
            value in allowed,
            key
            + " in "
            + source
            + " conflicts with user journals; administrator must approve "
            + key
            + "="
            + allowed[0]
            + ", apply journald policy and retry setup",
        )
    return values


def check_journal_path():
    ancestors(JOURNAL.parent)
    if os.path.lexists(str(JOURNAL)):
        info = JOURNAL.lstat()
        # systemd owns journal ACLs. Read-only ACL grants are normal; the mode's
        # ACL mask must still exclude every non-owner writer.
        require(
            stat.S_ISDIR(info.st_mode)
            and info.st_uid == OWNER
            and not info.st_mode & 0o022,
            "unsafe /var/log/journal; administrator must inspect ownership/links; do not recursively chown",
        )


def check_host_account(args):
    try:
        account = pwd.getpwnam(args.user)
    except KeyError:
        raise ReleaseError(
            "account missing; administrator must create "
            + args.user
            + " using the organisation's login-account procedure"
        ) from None
    require(
        account.pw_uid >= 1000
        and not 61184 <= account.pw_uid <= 65535
        and account.pw_gid != 0,
        "use an ordinary non-root login account with a per-user journal",
    )
    require(
        account.pw_shell in ("/bin/bash", "/usr/bin/bash", "/bin/sh", "/usr/bin/sh"),
        "account needs an interactive login shell; administrator must verify the account",
    )
    groups = command(["id", "-nG", args.user]).stdout.split()
    require(
        not {"root", "wheel", "adm", "systemd-journal"}.intersection(groups),
        "runtime account has privileged groups; administrator must use an unprivileged account",
    )
    result = command(["sudo", "-n", "-l", "-U", args.user], allowed=(0, 1))
    denial = (
        r"User " + re.escape(args.user) + r" is not allowed to run sudo on [^\n]+\."
    )
    lines = (result.stdout + result.stderr).strip()
    # OL9 sudo may return zero for a successful policy query with no grants.
    # The complete explicit denial, not the query exit code, proves no access.
    require(
        re.fullmatch(denial, lines),
        "sudo policy grants access or could not be verified; administrator must check "
        "sudo -l -U " + args.user + " and use an account with no grants",
    )
    root = BASE / args.product
    require(
        Path(account.pw_dir) != root,
        "old service-home layout is not migrated; use a separate ordinary login account",
    )
    ancestors(BASE)
    if os.path.lexists(str(root)):
        protected(root, directory=True)
        require(
            stat.S_IMODE(root.stat().st_mode) == 0o755,
            "product root must have mode 0755",
        )
        for name in ("state", "config", "storage"):
            path = root / name
            if os.path.lexists(str(path)):
                info = path.lstat()
                require(
                    stat.S_ISDIR(info.st_mode) and info.st_uid == account.pw_uid,
                    "foreign or linked "
                    + str(path)
                    + "; administrator must inspect; no automatic takeover",
                )
    dropins = SYSTEMD / ("user@" + str(account.pw_uid) + ".service.d")
    if os.path.lexists(str(dropins)):
        ancestors(dropins)
        expected = dropins / ("podman-offline-" + args.product + ".conf")
        for path in dropins.glob("podman-offline-*.conf"):
            require(
                path == expected,
                "account already runs another product; use a separate account",
            )
        if os.path.lexists(str(expected)):
            protected(expected)
            wanted = (
                "# Managed by podman-offline scripts/prepare-host.sh for product "
                + args.product
                + ".\n[Service]\nEnvironment=XDG_CONFIG_HOME="
                + str(root / "config")
                + " XDG_DATA_HOME="
                + str(root / "storage")
                + "\n"
            )
            require(
                expected.read_text() == wanted,
                "conflicting user-manager drop-in; administrator must inspect "
                + str(expected),
            )
    return account


def check_host_prerequisites(args, selections, after_lock=False):
    """Read-only checks before product_lock creates any product paths."""
    errors = []

    def check(action):
        try:
            return action()
        except (
            ReleaseError,
            OSError,
            ValueError,
            KeyError,
            subprocess.TimeoutExpired,
        ) as error:
            errors.append(error_message(error))
            return None

    required = {
        "gpgv": "gnupg2",
        "fapolicyd-cli": "fapolicyd",
        "getenforce": "libselinux-utils",
        "semanage": "policycoreutils-python-utils",
        "restorecon": "policycoreutils",
        "loginctl": "systemd",
        "systemctl": "systemd",
        "systemd-analyze": "systemd",
        "systemd-tmpfiles": "systemd",
        "journalctl": "systemd",
        "firewall-cmd": "firewalld",
        "newuidmap": "shadow-utils-subid",
        "newgidmap": "shadow-utils-subid",
        "setpriv": "util-linux",
        "usermod": "shadow-utils",
        "getfacl": "acl",
        "sudo": "sudo",
        "podman": "podman",
        "bash": "bash",
        "python3": "python3",
        "id": "coreutils",
        "getent": "glibc-common",
    }
    for executable, package in required.items():
        if shutil.which(executable) is None:
            errors.append(
                "missing "
                + executable
                + "; administrator must install OL9 package "
                + package
                + " from the approved offline repository"
            )

    def host_policy():
        os_release = OS_RELEASE.read_text()
        require(
            re.search(r"^ID=[\"\']?ol[\"\']?$", os_release, re.MULTILINE)
            and re.search(
                r"^VERSION_ID=[\"\']?9(?:\.\d+)?[\"\']?$", os_release, re.MULTILINE
            ),
            "Oracle Linux 9 required; use the supported host baseline",
        )
        require(
            command(["getenforce"]).stdout.strip() == "Enforcing",
            "SELinux must be Enforcing; administrator must correct the host baseline",
        )
        for service in ("fapolicyd", "firewalld"):
            require(
                command(
                    ["systemctl", "is-active", service], allowed=(0, 3)
                ).stdout.strip()
                == "active",
                service
                + " must be active; administrator must start the approved service",
            )
        ancestors(FAPOLICYD.parent)
        protected(FAPOLICYD)
        policy = setting_values(FAPOLICYD.read_text())
        require(
            policy.get("permissive", "0") == "0",
            "fapolicyd permissive mode is not supported; correct host policy",
        )
        require(
            policy.get("integrity") in ("none", "size", "sha256"),
            "unsupported fapolicyd integrity policy",
        )
        require(
            policy.get("subj_cache_size", "").isdigit()
            and int(policy["subj_cache_size"]) >= 16381,
            "set subj_cache_size = 16381 in /etc/fapolicyd/fapolicyd.conf and restart fapolicyd as administrator before retry",
        )

    check(host_policy)
    account = check(lambda: check_host_account(args))
    check(
        lambda: journal_settings(
            command(["systemd-analyze", "cat-config", "systemd/journald.conf"]).stdout
        )
    )
    check(check_journal_path)

    def inputs():
        sizes = [regular_size(path) for item in selections for path in item[2:]]
        regular_size(args.keyring)
        require(
            input_digest(args.keyring) == args.key_sha256,
            "keyring digest mismatch; obtain the correct public key and independent SHA256",
        )
        retained = BASE / args.product / "keyring.gpg"
        if os.path.lexists(str(retained)):
            protected(retained)
            require(
                digest(retained) == args.key_sha256,
                "existing keyring differs; key rotation is a separate administrator action",
            )
        check_space([(BASE, sum(sizes)), (TMP, 0), (JOURNAL.parent, 0)])

    check(inputs)
    require(
        not errors,
        (
            "recheck failed after locking the product anchor (no publication/host work):\n- "
            if after_lock
            else "preflight failed before changes:\n- "
        )
        + "\n- ".join(errors),
    )
    print(
        "PASS: setup preflight; space checks are lower bounds, not application sizing",
        flush=True,
    )
    return account


def prepare_persistent_journal():
    # Repeat policy/path checks immediately before host-wide effects.
    journal_settings(
        command(["systemd-analyze", "cat-config", "systemd/journald.conf"]).stdout
    )
    check_journal_path()
    created = not JOURNAL.exists()
    if created:
        JOURNAL.mkdir(mode=0o755)
    command(["systemd-tmpfiles", "--create", "--prefix", str(JOURNAL)])
    command(["journalctl", "--flush"])
    check_journal_path()
    require(
        any(JOURNAL.glob("*/*.journal")),
        "journal flush did not establish persistent storage; administrator must check journald disk/policy, then retry setup",
    )
    print(
        "PASS: persistent journal "
        + ("created (host-wide)" if created else "verified"),
        flush=True,
    )


def verify_host_setup(args, account):
    root = BASE / args.product
    protected(root, directory=True)
    for name in ("state", "config", "storage"):
        path = root / name
        info = path.lstat()
        require(
            stat.S_ISDIR(info.st_mode)
            and info.st_uid == account.pw_uid
            and stat.S_IMODE(info.st_mode) == 0o700,
            "host directory postcondition failed: " + str(path),
        )
    require(
        command(
            ["loginctl", "show-user", args.user, "-p", "Linger", "--value"]
        ).stdout.strip()
        == "yes",
        "linger is not enabled; retry setup and inspect loginctl as administrator",
    )
    environment = command(
        ["systemctl", "--user", "-M", args.user + "@", "show-environment"]
    ).stdout.splitlines()
    for variable, name in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "storage")):
        require(
            variable + "=" + str(root / name) in environment,
            "user manager environment postcondition failed; rerun setup as administrator",
        )
    for scope in ([], ["--permanent"]):
        require(
            command(
                ["firewall-cmd"] + scope + ["--query-port=" + str(args.port) + "/tcp"],
                allowed=(0, 1),
            ).returncode
            == 0,
            "HTTPS firewall port is not active/permanent; retry setup as administrator",
        )
    check_journal_path()
    require(
        any(JOURNAL.glob("*/*.journal")),
        "persistent journal is unavailable; retry setup",
    )


def setup_host(args, selections):
    """Compose existing authorities; never create runtime install receipts."""
    check_host_prerequisites(args, selections)
    with product_lock(args.product) as root:
        account = check_host_prerequisites(args, selections, after_lock=True)
        provision_key(root, args.keyring, args.key_sha256)
        for component, version, archive, signature in selections:
            with diagnostic(
                "prepare selected release",
                Path(identity(args.product, component, version)),
            ):
                path = publish(
                    root,
                    archive,
                    signature,
                    args.product,
                    component,
                    version,
                    setup_space=True,
                )
                enroll(path)
            print("PASS: release ready " + str(path), flush=True)
        component, version = args.host_release.split("@")
        host = release_path(args.product, component, version)
        record = published(host)
        script = host / "scripts/prepare-host.sh"
        require(
            "scripts/prepare-host.sh" in record["files"]
            and digest(script) == record["files"]["scripts/prepare-host.sh"]["sha256"],
            "selected host release has no authenticated host script; obtain the correct signed bundle",
        )
        prepare_persistent_journal()
        command(
            [
                "/usr/bin/bash",
                str(script),
                "--port",
                str(args.port),
                "--user",
                args.user,
            ]
        )
        print("PASS: existing host preparation", flush=True)
        verify_host_setup(args, account)
        print(
            "PASS: host setup; product="
            + args.product
            + " account="
            + args.user
            + " HTTPS="
            + str(args.port)
            + "; application installation is next",
            flush=True,
        )
        print(
            "NEXT: log in with ssh as "
            + args.user
            + ", then run:\n"
            + "bash "
            + shlex.quote(str(host / "deploy.sh"))
            + " init-layout",
            flush=True,
        )


def provision_key(root, keyring, key_sha256):
    require(
        keyring is not None
        and key_sha256 is not None
        and re.fullmatch(r"[0-9a-f]{64}", key_sha256),
        "keyring and independent key SHA256 required",
    )
    target = root / "keyring.gpg"
    with tempfile.TemporaryDirectory(prefix=".key-", dir=str(root)) as directory:
        snapshot = Path(directory) / "keyring"
        copy_input(keyring, snapshot)
        require(
            digest(snapshot) == key_sha256,
            "keyring authentication mismatch",
        )
        snapshot.chmod(0o644)
        if os.path.lexists(str(target)):
            protected(target)
            require(digest(target) == digest(snapshot), "existing keyring differs")
        else:
            with snapshot.open("rb") as stream:
                os.fsync(stream.fileno())
            os.rename(str(snapshot), str(target))
            sync_directory(root)
    print("PASS: independent keyring provisioned")


def release_path(product, component, version):
    return BASE / product / "releases" / identity(product, component, version)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation",
        choices=(
            "provision-key",
            "publish",
            "prepare",
            "wait",
            "withdraw",
            "retire",
            "setup",
        ),
    )
    parser.add_argument("--product", required=True)
    parser.add_argument("--component")
    parser.add_argument("--version")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--signature", type=Path)
    parser.add_argument(
        "--keyring",
        type=Path,
        help="input keyring for provision-key/setup only; publish/prepare always use the pinned product key",
    )
    parser.add_argument("--key-sha256")
    parser.add_argument("--old-version")
    parser.add_argument("--user")
    parser.add_argument("--port", type=int)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--release", action="append", default=[])
    parser.add_argument("--host-release")
    args = parser.parse_args()
    setup_fields = (
        args.user,
        args.port,
        args.input_dir,
        args.release,
        args.host_release,
    )
    if args.operation != "setup" and any(
        value is not None and value != [] for value in setup_fields
    ):
        parser.error("setup arguments are only accepted for setup")
    if args.operation == "setup":
        try:
            request = setup_request(args)
        except ReleaseError as error:
            parser.error(str(error))
        require(
            os.geteuid() == 0,
            "root required; run the setup command as administrator with sudo",
        )
        os.umask(0o022)
        # No caller-controlled shell startup, Python path or executable search.
        os.environ.clear()
        os.environ.update(PATH="/usr/sbin:/usr/bin:/sbin:/bin", LC_ALL="C")
        try:
            setup_host(args, request)
        except (
            ReleaseError,
            OSError,
            ValueError,
            KeyError,
            tarfile.TarError,
            subprocess.TimeoutExpired,
            yaml.YAMLError,
        ) as error:
            raise ReleaseError(
                "setup: "
                + error_message(error)
                + "; fix the named step using docs/PRODUCTION-INSTALL.md, then rerun the same administrator setup command (completed releases are retained)"
            ) from None
        return
    require(os.geteuid() == 0, "root required")
    if args.operation != "provision-key":
        identity(args.product, args.component, args.version)
    os.umask(0o022)
    require(
        args.operation == "provision-key" or args.keyring is None,
        "--keyring is only accepted for provision-key; publication uses the pinned product key",
    )
    context = diagnostic(args.operation, BASE / args.product)
    with context, product_lock(args.product) as root:
        if args.operation == "provision-key":
            provision_key(root, args.keyring, args.key_sha256)
            return
        path = release_path(args.product, args.component, args.version)
        if args.operation in ("publish", "prepare"):
            require(
                all((args.archive, args.signature)),
                "archive and detached signature required; unsigned production bundles are refused",
            )
            path = publish(
                root,
                args.archive,
                args.signature,
                args.product,
                args.component,
                args.version,
            )
            if args.operation == "prepare":
                enroll(path)
        elif args.operation == "wait":
            old = (
                release_path(args.product, args.component, args.old_version)
                if args.old_version
                else None
            )
            wait_trust(path, old)
        elif args.operation == "withdraw":
            withdraw(path)
        else:
            require(
                args.old_version and args.old_version != args.version,
                "distinct old version required",
            )
            old = release_path(args.product, args.component, args.old_version)
            published(path)
            retire(root, path, old)
        print("PASS: protected release " + args.operation, flush=True)


if __name__ == "__main__":
    try:
        main()
    except (
        ReleaseError,
        OSError,
        ValueError,
        KeyError,
        tarfile.TarError,
        subprocess.TimeoutExpired,
        yaml.YAMLError,
    ) as error:
        raise SystemExit("ERROR: release: " + error_message(error)) from None
