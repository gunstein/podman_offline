"""Production installation paths outside the login home (backlog 64).

The account's registered home (common.HOME) only identifies the user and holds
the small bootstrap file ~/.<product>/<product>.env. Everything else the
product keeps lives under the root-owned installation root /var/lib/<product>:

    releases/   root-owned, published by scripts/release.py
    state/      component config, credentials, metadata, registrations, retry record
    config/     XDG_CONFIG_HOME of Podman and the user's systemd manager (Quadlets)
    storage/    XDG_DATA_HOME of Podman (images, volumes, caches)

select() is the single place that reads the bootstrap file and assigns the
production paths in common; it runs only for production commands from an
unpacked release, never in source dev or bundle building. It reads data, never
executes it, and reads no credential contents.
"""

import ctypes
import errno
import os
import re
import stat
import subprocess
import uuid
from pathlib import Path

from . import common

# Root-owned parent of every installation root; tests replace it.
ANCHOR = Path("/var/lib")
# The owner a protected root and its ancestors must have, and the highest
# ancestor checked; tests replace both.
ROOT_UID = 0
TRUSTED_TOP = Path("/")
FIELDS = ("INSTALL_ROOT",)
MAX_BOOTSTRAP_SIZE = 64 * 1024
LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
PLAIN_PATH = re.compile(r"^/[A-Za-z0-9._/-]*$")
# Podman and the user's systemd manager must agree on these two variables.
DIRECTORIES = {"XDG_CONFIG_HOME": "config", "XDG_DATA_HOME": "storage"}


def bootstrap_path(product):
    """~/.<product>/<product>.env in the account's registered home."""
    return common.HOME / ("." + product) / (product + ".env")


def expected_root(product):
    return ANCHOR / product


def publish_bootstrap(directory, temporary, name):
    """Linux rename without replacement, including a concurrently created file.

    A hard-link/unlink pair leaves two links if killed between operations;
    bootstrap readers deliberately reject linked files. Use one atomic rename.
    """
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        rename = libc.renameat2
    except AttributeError:
        raise common.DeployError(
            "init-layout requires Linux renameat2 support"
        ) from None
    rename.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    rename.restype = ctypes.c_int
    if rename(directory, os.fsencode(temporary), directory, os.fsencode(name), 1):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), name)


def initialize(product):
    """Explicit, no-clobber bootstrap creation after administrator preparation."""
    root = expected_root(product)
    check_root(root)
    check_home_unused(product)
    path = bootstrap_path(product)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with_dir = os.open(str(common.HOME), flags)
    try:
        try:
            os.mkdir(path.parent.name, 0o700, dir_fd=with_dir)
        except FileExistsError:
            pass
        directory = os.open(path.parent.name, flags, dir_fd=with_dir)
        try:
            info = os.fstat(directory)
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise common.DeployError(
                    f"{path.parent} must be owned by you with mode 0700"
                )
            if os.path.lexists(str(path)):
                install_root(product, read_bootstrap(path), path)
                print(f"[OK] Existing bootstrap retained: {path}")
                return
            temporary = ".bootstrap-" + uuid.uuid4().hex
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
            try:
                with os.fdopen(fd, "w") as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write(f"INSTALL_ROOT={root}\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    publish_bootstrap(directory, temporary, path.name)
                except FileExistsError:
                    install_root(product, read_bootstrap(path), path)
                    print(f"[OK] Existing bootstrap retained: {path}")
                    return
            finally:
                # Only this attempt's private temporary name is cleaned up.
                # SIGKILL may leave residue, but no partial authoritative file.
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
            os.fsync(directory)
            os.fsync(with_dir)
        finally:
            os.close(directory)
    finally:
        os.close(with_dir)
    print(f"[OK] Bootstrap ready: {path}; continue with init-config from the manual")


def read_bootstrap(path):
    """Return the supported fields of a private KEY=VALUE file; never executes it.

    Blank lines and lines starting with # are ignored. Every other line must be
    KEY=VALUE. Unknown keys (for example application settings kept in the same
    file) are ignored: they are not validated, logged, exported or forwarded to
    containers. A supported field may appear once; one pair of surrounding
    single or double quotes is removed, with no escapes or substitutions.
    Errors name the file, line and key, never a value.
    """
    text = private_text(path)
    values = {}
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = LINE.match(stripped)
        if match is None:
            raise common.DeployError(
                f"{path} line {number}: expected KEY=VALUE; the file is read as "
                "data, not as a shell script"
            )
        key, value = match.groups()
        if key not in FIELDS:
            continue
        if key in values:
            raise common.DeployError(f"{path} line {number}: duplicate {key}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key] = (value, number)
    missing = [key for key in FIELDS if key not in values]
    if missing:
        raise common.DeployError(f"{path}: missing {', '.join(missing)}")
    return values


def private_text(path):
    """Read the bootstrap file only from a private, user-owned, unlinked location."""
    directory = path.parent
    try:
        info = directory.lstat()
    except FileNotFoundError:
        raise common.DeployError(missing_message(path)) from None
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise common.DeployError(f"{directory} must be a directory owned by you")
    if info.st_mode & 0o077:
        raise common.DeployError(f"{directory} must have mode 0700")
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        raise common.DeployError(missing_message(path)) from None
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise common.DeployError(
                f"Refuse symlinked bootstrap file {path}"
            ) from None
        raise
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise common.DeployError(f"{path} must be a regular file without links")
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise common.DeployError(f"{path} must be owned by you with mode 0600")
        if info.st_size > MAX_BOOTSTRAP_SIZE:
            raise common.DeployError(
                f"{path} is larger than {MAX_BOOTSTRAP_SIZE} bytes"
            )
        data = stream.read(MAX_BOOTSTRAP_SIZE + 1)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise common.DeployError(f"{path} must be UTF-8 text") from None


def missing_message(path):
    product = path.stem
    return (
        f"Missing {path}. Create it (directory 0700, file 0600) with the line "
        f"INSTALL_ROOT={expected_root(product)}; see docs/PRODUCTION-INSTALL.md"
    )


def install_root(product, values, path):
    """The validated installation root; only /var/lib/<product> is supported."""
    value, number = values["INSTALL_ROOT"]
    expected = expected_root(product)
    if not PLAIN_PATH.match(value) or Path(value) != expected or ".." in value:
        raise common.DeployError(
            f"{path} line {number}: INSTALL_ROOT must be {expected} for product {product}"
        )
    return expected


def check_protected(path):
    """A root-owned directory no other user can replace or write; no ACL grants."""
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != ROOT_UID
        or info.st_mode & 0o022
    ):
        raise common.DeployError(
            f"{path} must be a root-owned directory without group/other write "
            "access; ask the administrator to run scripts/prepare-host.sh"
        )
    check_no_acl(path)


def check_no_acl(path):
    for attribute in ("system.posix_acl_access", "system.posix_acl_default"):
        try:
            os.getxattr(str(path), attribute, follow_symlinks=False)
        except OSError as error:
            if error.errno not in (errno.ENODATA, errno.ENOTSUP):
                raise
        else:
            raise common.DeployError(f"Refuse ACL on installation path {path}")


def check_private(path):
    """A directory prepared for this account: owned by it, mode 0700, no links."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise common.DeployError(
            f"Missing {path}; ask the administrator to run scripts/prepare-host.sh "
            "for this account"
        ) from None
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise common.DeployError(f"{path} must be a directory owned by you")
    if info.st_mode & 0o077:
        raise common.DeployError(f"{path} must have mode 0700")
    check_no_acl(path)


def check_root(root):
    """The root and every ancestor are protected; then the account's own directories."""
    chain = [root]
    while chain[-1] != TRUSTED_TOP and chain[-1] != chain[-1].parent:
        chain.append(chain[-1].parent)
    for path in reversed(chain):
        check_protected(path)
    for name in ("state",) + tuple(DIRECTORIES.values()):
        check_private(root / name)


def check_home_unused(product):
    """Refuse product Quadlets in the login home instead of running two installations.

    Only new installations under the root are supported; nothing is migrated.
    """
    quadlets = common.HOME / ".config/containers/systemd"
    found = (
        sorted(quadlets.glob(product + ".network"))
        + sorted(quadlets.glob(product + "-*.kube"))
        if quadlets.is_dir()
        else []
    )
    if found:
        raise common.DeployError(
            f"Found {found[0]} from an installation in the login home. This release "
            "installs only new installations under the installation root and does "
            "not migrate; remove the old installation first"
        )


def environment(root):
    return {name: str(root / directory) for name, directory in DIRECTORIES.items()}


def select(product):
    """Read the bootstrap file, validate the root and assign the production paths.

    The deploy process exports XDG_CONFIG_HOME/XDG_DATA_HOME only to its own
    children (Podman); the user's shell and other processes are unchanged.
    """
    path = bootstrap_path(product)
    root = install_root(product, read_bootstrap(path), path)
    check_root(root)
    check_home_unused(product)
    common.STATE = root / "state"
    common.FILES_DIR = common.STATE / "files"
    common.QUADLET_DIR = root / DIRECTORIES["XDG_CONFIG_HOME"] / "containers/systemd"
    common.QUADLET_TARGET = common.QUADLET_DIR / (common.STANDALONE_PRODUCT + ".kube")
    common.QUADLET_YAML = common.QUADLET_DIR / (common.STANDALONE_PRODUCT + ".yaml")
    os.environ.update(environment(root))
    return root


def check_user_manager(root):
    """Services must use the same Podman storage and Quadlets as this process.

    The administrator sets both variables in the user manager with a drop-in
    (scripts/prepare-host.sh); a terminal export cannot reach the Quadlet
    generator or services started at boot. Read-only host query.
    """
    result = subprocess.run(  # noqa: UP022 - Python 3.6
        ["systemctl", "--user", "show-environment"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,  # noqa: UP021 - Python 3.6
        check=False,
    )
    if result.returncode != 0:
        raise common.DeployError(
            "Cannot read the user systemd manager environment (systemctl --user "
            f"show-environment exit {result.returncode}); check linger and "
            "XDG_RUNTIME_DIR"
        )
    actual = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )
    for name, value in environment(root).items():
        if actual.get(name) != value:
            raise common.DeployError(
                f"The user systemd manager has {name}={actual.get(name, '')!r}, "
                f"expected {value!r}. Ask the administrator to run "
                "scripts/prepare-host.sh for this account (it installs the "
                "user@<uid>.service drop-in and restarts the user manager)"
            )
