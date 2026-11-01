"""<product>-admin: install delivered RPMs and prepare this host (backlog 69 WP2).

Phase 1: unsigned RPMs, within the product owner's decisions of 2026-11-01
(BACKLOG.md item 69). The <product>-tools RPM (rpms.py) installs this file as
/usr/libexec/<product>-tools/admin.py beside bundle.yaml (the product name),
scripts/prepare-host.sh and the two deployment modules it imports; the
command is /usr/sbin/<product>-admin.

    sudo <product>-admin <directory> [--user <account>] [--port <port>]
    sudo <product>-admin --credentials <directory>

Install, in this order, each step only after the previous one succeeded:

1. Ask for the runtime account and HTTPS port the first time; later they come
   from the host (the owner of /var/lib/<product>/state, /etc/<product>/host.conf).
2. Preflight: stop before any change and say who must act.
3. Copy this product's RPM files from the directory into a private root-only
   directory and decide from those copies: the newest version per component;
   refuse one older than installed, or one installed under the same name and
   version with other content; reinstall an identical one that fails rpm -V.
4. Newer tools first, then start the new command again with the same answers.
5. One offline dnf transaction for the releases.
6. Host preparation: persistent journal, prepare-host.sh, host.conf.
7. Run the newest release of each component once as the runtime account, so a
   release fapolicyd does not trust stops here and not in the runtime command.

Credentials: copy <directory>/<component>/credentials/... into
/var/lib/<product>/incoming/ with the same layout. Root reads the delivery; a
child process running as the runtime account writes, so root never writes
into the account's directories.
"""

import base64
import grp
import json
import os
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from collections import namedtuple
from pathlib import Path

import yaml

from deployment import arguments, output

log = output.log

TOOLS = Path(__file__).resolve().parent
# Host paths; tests point them at temporary files.
LIB = Path("/var/lib")
ETC = Path("/etc")
JOURNAL = Path("/var/log/journal")
OS_RELEASE = Path("/etc/os-release")
FAPOLICYD_CONF = Path("/etc/fapolicyd/fapolicyd.conf")
# Where a release RPM installs its tree (rpms.py); release RPMs are recognised by it.
RELEASE_PATH = "/var/lib/{product}/releases/{name}"

DEFAULT_PORT = 8443
TRUST_WAIT = 30  # seconds for fapolicyd to learn about newly installed files
CREDENTIAL_LIMIT = 1024 * 1024  # bytes per credential file
ID = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
PRIVILEGED_GROUPS = {"root", "wheel", "adm", "systemd-journal"}

# Phase 1 delivers unsigned RPMs (backlog 69, 2026-10-26). This is the one
# place that turns dnf's signature check off; phase 2 replaces it with a check
# against the product's key. No repository is contacted.
DNF = ["dnf", "--disablerepo=*", "--setopt=localpkg_gpgcheck=0", "-y", "-q"]

# Executables the product uses on the host, with the OL9 package providing each.
REQUIRED = {
    "rpm": "rpm",
    "dnf": "dnf",
    "setpriv": "util-linux",
    "getenforce": "libselinux-utils",
    "semanage": "policycoreutils-python-utils",
    "restorecon": "policycoreutils",
    "systemctl": "systemd",
    "systemd-analyze": "systemd",
    "systemd-tmpfiles": "systemd",
    "journalctl": "systemd",
    "loginctl": "systemd",
    "firewall-cmd": "firewalld",
    "newuidmap": "shadow-utils-subid",
    "newgidmap": "shadow-utils-subid",
    "usermod": "shadow-utils",
    "getfacl": "acl",
    "sudo": "sudo",
    "podman": "podman",
}

DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC

# One RPM file or installed package of this product. component is "" for the
# tools package; file is the private copy, or None for an installed package.
Package = namedtuple("Package", "name version component file")
QUERY = "%{NAME} %{VERSION} %{FILENAMES}\n"


class AdminError(Exception):
    """Error shown as a single ERROR line without a traceback."""


def run(command, check=True, capture=True, stdin=None):
    """Run a host command in the C locale; return the CompletedProcess."""
    log.debug("+ " + " ".join(command))
    pipe = subprocess.PIPE if capture else None
    result = subprocess.run(
        command,
        input=stdin,
        stdout=pipe,
        stderr=pipe,
        universal_newlines=True,  # noqa: UP021 - text= needs Python 3.7
        env=dict(os.environ, LC_ALL="C"),
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        raise AdminError(
            f"{command[0]} {command[1]} failed (exit {result.returncode})"
            + (": " + detail[-1] if detail else "")
        )
    return result


def product_name():
    return yaml.safe_load((TOOLS / "bundle.yaml").read_text())["product"]


def version_key(version):
    return tuple(int(part) for part in version.split("."))


def as_account(account):
    """Run the rest of a command as the runtime account, without any privilege."""
    return [
        "setpriv",
        f"--reuid={account.pw_uid}",
        f"--regid={account.pw_gid}",
        "--clear-groups",
        "--inh-caps=-all",
        "--ambient-caps=-all",
        "--bounding-set=-all",
        "--no-new-privs",
        "--",
    ]


# Answers -----------------------------------------------------------------


def port_number(value):
    """argparse type: an unprivileged TCP port."""
    if not value.isdigit() or not 1024 <= int(value) <= 65535:
        raise ValueError(value)
    return int(value)


def ask(question, default, option):
    """Ask on the terminal; without one, name the option that gives the value."""
    if not sys.stdin.isatty():
        raise AdminError(f"Give {option}; there is no terminal to ask")
    prompt = f"{question} [{default}]: " if default else f"{question}: "
    answer = input(prompt).strip() or default
    if not answer:
        raise AdminError(f"No answer; run again and answer, or give {option}")
    return answer


def host_conf(product):
    return ETC / product / "host.conf"


def prepared_account(product):
    """The runtime account of a prepared host: the owner of state/, else None."""
    state = LIB / product / "state"
    if not state.is_dir() or state.is_symlink():
        return None
    return pwd.getpwuid(state.lstat().st_uid)


def answers(product, args):
    """The runtime account and HTTPS port: from the host once prepared, else asked.

    The owner of state/ is the account (prepare-host.sh creates it) and
    host.conf the port; neither is changed after the first preparation.
    """
    prepared = prepared_account(product)
    account = prepared.pw_name if prepared else None
    if account and args.user and args.user != account:
        raise AdminError(
            f"{product} runs as {account} on this host; another account is not supported"
        )
    account = (
        account
        or args.user
        or ask(
            "Runtime account (an existing login account without sudo)", None, "--user"
        )
    )
    port = None
    if host_conf(product).exists():
        match = re.search(
            r"^HTTPS_PORT=([0-9]+)$", host_conf(product).read_text(), re.MULTILINE
        )
        if not match:
            raise AdminError(f"{host_conf(product)} has no HTTPS_PORT line; inspect it")
        port = int(match.group(1))
    if port and args.port and args.port != port:
        raise AdminError(
            f"{product} uses HTTPS port {port} on this host; changing it is not supported"
        )
    if not port and not args.port:
        try:
            args.port = port_number(ask("HTTPS port", str(DEFAULT_PORT), "--port"))
        except ValueError:
            raise AdminError("The HTTPS port must be a number 1024-65535") from None
    return account, port or args.port


# Preflight ---------------------------------------------------------------


def check_os():
    text = OS_RELEASE.read_text()
    if not (
        re.search(r"^ID=[\"']?ol[\"']?$", text, re.MULTILINE)
        and re.search(r"^VERSION_ID=[\"']?9(\.[0-9]+)?[\"']?$", text, re.MULTILINE)
    ):
        raise AdminError("This host is not Oracle Linux 9; use a supported host")


def check_selinux():
    mode = run(["getenforce"]).stdout.strip()
    if mode != "Enforcing":
        raise AdminError(
            f"SELinux is {mode}; the system administrator sets it to Enforcing"
        )


def check_services():
    for service in ("firewalld", "fapolicyd"):
        state = run(["systemctl", "is-active", service], check=False).stdout.strip()
        if state != "active":
            raise AdminError(
                f"{service} is {state or 'not active'}; "
                "the system administrator starts and enables it"
            )


def check_fapolicyd():
    """What the product needs from fapolicyd (decision 5): trust in RPM files."""
    settings = {}
    for line in FAPOLICYD_CONF.read_text().splitlines():
        match = re.fullmatch(r"\s*([a-z_]+)\s*=\s*(.*?)\s*", line)
        if match:
            settings[match.group(1)] = match.group(2)
    trust = [item.strip() for item in settings.get("trust", "rpmdb,file").split(",")]
    if "rpmdb" not in trust:
        raise AdminError(
            f"fapolicyd does not trust the RPM database (trust = {settings['trust']} "
            f"in {FAPOLICYD_CONF}); the security administrator adds rpmdb"
        )
    cache = settings.get("subj_cache_size", "")
    if not cache.isdigit() or int(cache) < 16381:
        raise AdminError(
            f"Set subj_cache_size = 16381 in {FAPOLICYD_CONF} and restart fapolicyd "
            "(security administrator); a smaller cache denies Podman at start"
        )
    if run(["rpm", "-q", "rpm-plugin-fapolicyd"], check=False).returncode != 0:
        raise AdminError(
            "Install rpm-plugin-fapolicyd from the OS media (system administrator); "
            "without it fapolicyd does not trust newly installed RPM files"
        )


def check_journal():
    """User journals need persistent storage split per user."""
    values = {"Storage": "auto", "SplitMode": "uid"}
    section = ""
    text = run(["systemd-analyze", "cat-config", "systemd/journald.conf"]).stdout
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
        elif section == "Journal" and "=" in line and not line.startswith(("#", ";")):
            key, value = (part.strip() for part in line.split("=", 1))
            if key in values:
                values[key] = value
    if values["Storage"] not in ("auto", "persistent"):
        raise AdminError(
            f"journald has Storage={values['Storage']}; the system administrator "
            "allows persistent journals (Storage=auto or persistent)"
        )
    if values["SplitMode"] != "uid":
        raise AdminError(
            f"journald has SplitMode={values['SplitMode']}; "
            "the system administrator sets SplitMode=uid"
        )


def check_account(name):
    """An ordinary login account without sudo rights or privileged groups."""
    try:
        account = pwd.getpwnam(name)
    except KeyError:
        raise AdminError(
            f"Account {name} does not exist; create it with the organisation's "
            "normal procedure first"
        ) from None
    if account.pw_uid < 1000 or 61184 <= account.pw_uid <= 65535 or account.pw_gid == 0:
        raise AdminError(
            f"{name} has UID {account.pw_uid}; use an ordinary login account (UID 1000 or higher)"
        )
    if account.pw_shell.endswith(("/nologin", "/false")):
        raise AdminError(
            f"{name} cannot log in (shell {account.pw_shell}); use a login account"
        )
    groups = set()
    for gid in os.getgrouplist(name, account.pw_gid):
        try:
            groups.add(grp.getgrgid(gid).gr_name)
        except KeyError:
            groups.add(str(gid))
    privileged = sorted(groups & PRIVILEGED_GROUPS)
    if privileged:
        raise AdminError(
            f"{name} is in the privileged group(s) {', '.join(privileged)}; "
            "use an account without them"
        )
    result = run(["sudo", "-n", "-l", "-U", name], check=False)
    # Only the complete denial proves no grants; OL9 may exit 0 either way.
    denial = r"User " + re.escape(name) + r" is not allowed to run sudo on [^\n]+\."
    if not re.fullmatch(denial, (result.stdout + result.stderr).strip()):
        raise AdminError(
            f"{name} may use sudo, or its sudo rights could not be read "
            f"(sudo -l -U {name}); the runtime account must have no sudo rights"
        )


def preflight(account):
    """Every check before any change; all failures at once, each naming who acts."""
    missing = [
        f"{executable} is missing; install the OL9 package {package} from the OS media"
        for executable, package in REQUIRED.items()
        if shutil.which(executable) is None
    ]
    if missing:
        raise AdminError(
            "Preflight stopped before any change:\n- " + "\n- ".join(missing)
        )
    errors = []
    for check in (
        check_os,
        check_selinux,
        check_services,
        check_fapolicyd,
        check_journal,
        lambda: check_account(account),
    ):
        try:
            check()
        except (AdminError, OSError) as error:
            errors.append(str(error))
    if errors:
        raise AdminError(
            "Preflight stopped before any change:\n- " + "\n- ".join(errors)
        )
    log.info("[OK] preflight")


# Packages ----------------------------------------------------------------


def component_of(product, name, version, first_file):
    """'' for the tools package, the component for a release, None otherwise."""
    if name == product + "-tools":
        return ""
    prefix, suffix = product + "-", "-" + version
    if not (
        VERSION.fullmatch(version) and name.startswith(prefix) and name.endswith(suffix)
    ):
        return None
    component = name[len(prefix) : -len(suffix)]
    if ID.fullmatch(component) and first_file == RELEASE_PATH.format(
        product=product, name=name
    ):
        return component
    return None


def installed(product):
    """This product's installed packages, from the RPM database."""
    packages = []
    for line in run(["rpm", "-qa", "--queryformat", QUERY]).stdout.splitlines():
        name, version, first_file = (line.split(" ", 2) + ["", ""])[:3]
        component = component_of(product, name, version, first_file)
        if component is not None:
            packages.append(Package(name, version, component, None))
    return packages


def copy_regular(source, target):
    """Copy a regular file without following a link or opening a device."""
    try:
        descriptor = os.open(str(source), FILE_FLAGS)
    except OSError as error:
        raise AdminError(
            f"Cannot read {source} ({error.strerror}); deliver regular files"
        ) from None
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise AdminError(f"{source} is not a regular file; deliver regular files")
        with open(str(target), "xb") as copy:
            shutil.copyfileobj(stream, copy)


def delivered(product, directory, private):
    """Copy this product's RPM files into private; describe them from the copies."""
    packages = []
    for entry in sorted(os.listdir(str(directory))):
        if not (entry.startswith(product + "-") and entry.endswith(".rpm")):
            continue
        copy = private / entry
        copy_regular(directory / entry, copy)
        line = run(["rpm", "-qp", "--queryformat", QUERY, str(copy)]).stdout
        name, version, first_file = (line.strip().split(" ", 2) + ["", ""])[:3]
        component = component_of(product, name, version, first_file)
        if component is None:
            log.warning(f"WARNING: {entry} is not a {product} package; ignored")
            continue
        packages.append(Package(name, version, component, copy))
    return packages


def content(query, target):
    """Each file's path, size, digest, mode, owner, group and link; not mtime."""
    lines = run(["rpm", query, "--dump", target]).stdout.splitlines()
    return [line.split(" ")[:2] + line.split(" ")[3:] for line in lines]


def select(product, delivery, packages):
    """Return (install, reinstall): newest delivered per component, checked.

    One version has one content: a package installed under the same name and
    version must have the same files. An older version than installed is
    refused, so a downgrade never reaches the runtime command.
    """
    newest = {}
    for package in delivery:
        current = newest.get(package.component)
        if current is None or version_key(package.version) > version_key(
            current.version
        ):
            newest[package.component] = package
    install, reinstall = [], []
    for component, package in sorted(newest.items()):
        versions = [p.version for p in packages if p.component == component]
        latest = max(versions, key=version_key) if versions else None
        if package.version in versions:
            if content("-qp", str(package.file)) != content("-q", package.name):
                raise AdminError(
                    f"{package.file.name}: {package.name} {package.version} is installed "
                    "with other content; one version has one content, so ask the "
                    "supplier for a new version"
                )
            if run(["rpm", "-V", package.name], check=False).returncode != 0:
                log.warning(
                    f"WARNING: installed {package.name} {package.version} is damaged "
                    "(rpm -V); reinstalling it"
                )
                reinstall.append(package)
            else:
                log.info(f"[OK] {package.name} {package.version} is installed")
        elif latest and version_key(latest) > version_key(package.version):
            raise AdminError(
                f"{package.file.name} is older than the installed "
                f"{component or 'tools'} {latest}; deliver {latest} or newer"
            )
        else:
            install.append(package)
    return install, reinstall


def restart(product, args, account, port):
    """Run the newly installed tools with the same delivery and answers."""
    command = f"/usr/sbin/{product}-admin"
    argv = [command, str(args.directory), "--user", account, "--port", str(port)]
    if args.verbose:
        argv.append("--verbose")
    sys.stdout.flush()
    os.execv(command, argv)


def install_packages(product, args, account, port):
    """Steps 3 to 5; returns only when the newest tools are running."""
    directory = Path(args.directory)
    if not directory.is_dir():
        raise AdminError(
            f"{directory} is not a directory; mount the medium or give the directory "
            "with the RPM files"
        )
    private = Path(tempfile.mkdtemp(prefix=product + "-admin-"))  # 0700, root
    try:
        install, reinstall = select(
            product, delivered(product, directory, private), installed(product)
        )
        tools = [package for package in install if not package.component]
        if tools:
            run(DNF + ["install", str(tools[0].file)])
            log.info(f"[OK] installed {tools[0].name} {tools[0].version}; starting it")
            shutil.rmtree(str(private))
            restart(product, args, account, port)
        if reinstall:
            run(DNF + ["reinstall"] + [str(package.file) for package in reinstall])
        if install:
            run(DNF + ["install"] + [str(package.file) for package in install])
        for package in reinstall + install:
            log.info(f"[OK] installed {package.name}")
    finally:
        shutil.rmtree(str(private), ignore_errors=True)


# Host --------------------------------------------------------------------


def prepare_host(product, account, port):
    """Step 6: persistent journal, prepare-host.sh, then host.conf."""
    # A volatile journal is not split per user: the runtime account could not
    # read its own service logs. OL9's default Storage=auto keeps the journal
    # persistent once this directory exists.
    if not JOURNAL.is_dir():
        JOURNAL.mkdir(mode=0o755)
        log.info(f"[OK] persistent journal enabled for the whole host ({JOURNAL})")
    run(["systemd-tmpfiles", "--create", "--prefix", str(JOURNAL)])
    run(["journalctl", "--flush"])
    script = TOOLS / "scripts/prepare-host.sh"
    command = ["bash", str(script), "--port", str(port), "--user", account.pw_name]
    if run(command, check=False, capture=False).returncode != 0:
        raise AdminError(
            f"Host preparation stopped; fix what it names, then run sudo {product}-admin again"
        )
    # The one source of the port for the runtime command; public, root-owned.
    directory = ETC / product
    directory.mkdir(mode=0o755, exist_ok=True)
    partial = directory / "host.conf.partial"
    partial.write_text(
        f"# Written by {product}-admin: the HTTPS port opened in the firewall.\n"
        f"HTTPS_PORT={port}\n"
    )
    partial.chmod(0o644)
    os.replace(str(partial), str(host_conf(product)))


def check_trust(product, account, packages):
    """Step 7: run the newest release of each component as the runtime account.

    deploy.sh --help imports the release's Python modules, which fapolicyd
    denies to a non-root account unless it trusts the files. fapolicyd learns
    about new RPM files shortly after the transaction, so retry for a while.
    """
    newest = {}
    for package in packages:
        current = newest.get(package.component)
        if package.component and (
            current is None
            or version_key(package.version) > version_key(current.version)
        ):
            newest[package.component] = package
    if not newest:
        log.warning(
            f"WARNING: no {product} release is installed yet; deliver the release RPMs"
        )
    for _, package in sorted(newest.items()):
        release = Path(RELEASE_PATH.format(product=product, name=package.name))
        command = as_account(account) + [
            "env",
            "-i",
            f"HOME={account.pw_dir}",
            "PATH=/usr/bin:/bin",
            "LANG=C.UTF-8",
            "bash",
            str(release / "deploy.sh"),
            "--help",
        ]
        deadline = time.monotonic() + TRUST_WAIT
        while True:
            result = run(command, check=False)
            if result.returncode == 0:
                break
            if time.monotonic() >= deadline:
                detail = (result.stderr or "").strip().splitlines()
                raise AdminError(
                    f"{account.pw_name} cannot run {release}/deploy.sh"
                    + (f" ({detail[-1]})" if detail else "")
                    + "; fapolicyd must trust RPM-installed files: the security "
                    "administrator checks fapolicyd-cli --list and the audit log, "
                    f"then run sudo {product}-admin again"
                )
            time.sleep(1)
        log.info(f"[OK] {account.pw_name} can run {package.name}")


def install(product, args):
    account_name, port = answers(product, args)
    preflight(account_name)
    account = pwd.getpwnam(account_name)
    install_packages(product, args, account_name, port)
    prepare_host(product, account, port)
    check_trust(product, account, installed(product))
    log.info(
        f"[OK] next: log in as {account_name} (at the console, or ssh "
        f"{account_name}@<server>); releases are in {LIB / product / 'releases'}"
    )


# Credentials -------------------------------------------------------------


def read_file(parent, name, path):
    try:
        descriptor = os.open(name, FILE_FLAGS, dir_fd=parent)
    except OSError as error:
        raise AdminError(f"Cannot read {path} ({error.strerror})") from None
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise AdminError(
                f"{path} is not a regular file; deliver regular files only"
            )
        if info.st_size > CREDENTIAL_LIMIT:
            raise AdminError(
                f"{path} is larger than {CREDENTIAL_LIMIT} bytes; is it a credential?"
            )
        return stream.read()


def read_tree(parent, name, path, relative, files):
    """Add every regular file below parent/name to files; refuse links and specials."""
    descriptor = os.open(name, DIRECTORY_FLAGS, dir_fd=parent)
    try:
        for entry in sorted(os.listdir(descriptor)):
            info = os.stat(entry, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                read_tree(
                    descriptor, entry, f"{path}/{entry}", f"{relative}/{entry}", files
                )
            elif stat.S_ISREG(info.st_mode):
                files[f"{relative}/{entry}"] = read_file(
                    descriptor, entry, f"{path}/{entry}"
                )
            else:
                raise AdminError(
                    f"{path}/{entry} is a link or special file; deliver regular files only"
                )
    finally:
        os.close(descriptor)


def read_credentials(product, directory, components):
    """{<component>/credentials/...: bytes} from every <component>/credentials/."""
    files = {}
    top = os.open(str(directory), DIRECTORY_FLAGS)
    try:
        for entry in sorted(os.listdir(top)):
            info = os.stat(entry, dir_fd=top, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode):
                continue
            inner = os.open(entry, DIRECTORY_FLAGS, dir_fd=top)
            try:
                if "credentials" not in os.listdir(inner):
                    continue
                if entry not in components:
                    raise AdminError(
                        f"{directory / entry}/credentials: no {product} release of "
                        f"{entry} is installed; check the directory name"
                    )
                read_tree(
                    inner,
                    "credentials",
                    f"{directory / entry}/credentials",
                    f"{entry}/credentials",
                    files,
                )
            finally:
                os.close(inner)
    finally:
        os.close(top)
    return files


# Runs as the runtime account through python3 -c, so no Python file is opened:
# fapolicyd denies an account untrusted Python files. stdin: {path: base64}.
# Stops before writing anything when a delivered file differs from one already
# in incoming/; writes each new file through a .partial name, so an interrupted
# copy is replaced by the next run.
WRITE_INCOMING = r"""
import base64, json, os, stat, sys

DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
files = {k: base64.b64decode(v) for k, v in json.load(sys.stdin).items()}


def directory(path, create):
    fd = os.open(sys.argv[1], DIRECTORY)
    for part in path.split("/"):
        try:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, DIRECTORY, dir_fd=fd)
        finally:
            os.close(fd)
        fd = child
        if os.fstat(fd).st_uid != os.geteuid():
            os.close(fd)
            raise SystemExit("ERROR: incoming/" + path + " belongs to another account; inspect it")
    return fd


def existing(path):
    parent, name = path.rsplit("/", 1)
    try:
        fd = directory(parent, create=False)
    except FileNotFoundError:
        return None
    try:
        try:
            handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        except FileNotFoundError:
            return None
        with os.fdopen(handle, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise SystemExit("ERROR: incoming/" + path + " is not a regular file; inspect it")
            return stream.read()
    finally:
        os.close(fd)


current = {path: existing(path) for path in sorted(files)}
different = [p for p, data in current.items() if data is not None and data != files[p]]
if different:
    raise SystemExit(
        "ERROR: incoming/" + ", incoming/".join(different) + " already exist with "
        "other content; nothing was copied. Remove them as the runtime account if "
        "the delivered files are right, then run again"
    )
for path, data in sorted(files.items()):
    if current[path] is not None:
        print("[OK] incoming/" + path + " is already there")
        continue
    parent, name = path.rsplit("/", 1)
    fd = directory(parent, create=True)
    try:
        try:
            os.unlink(name + ".partial", dir_fd=fd)
        except FileNotFoundError:
            pass
        handle = os.open(
            name + ".partial",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=fd,
        )
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.rename(name + ".partial", name, src_dir_fd=fd, dst_dir_fd=fd)
    finally:
        os.close(fd)
    print("[OK] incoming/" + path)
"""


def hand_over_credentials(product, directory):
    """Copy delivered credentials into incoming/ as the runtime account."""
    incoming = LIB / product / "incoming"
    account = prepared_account(product)
    if account is None or account.pw_uid == 0 or not incoming.is_dir():
        raise AdminError(
            f"{incoming} is not prepared; first run sudo {product}-admin <delivery directory>"
        )
    components = {package.component for package in installed(product)}
    files = read_credentials(product, directory, components - {""})
    if not files:
        raise AdminError(
            f"No <component>/credentials/ directory in {directory}; see the manual for the layout"
        )
    payload = json.dumps(
        {path: base64.b64encode(data).decode("ascii") for path, data in files.items()}
    )
    command = as_account(account) + [
        "python3", "-I", "-B", "-c", WRITE_INCOMING, str(incoming),
    ]  # fmt: skip
    result = run(command, check=False, stdin=payload)
    for line in result.stdout.splitlines():
        log.info(line)
    if result.returncode != 0:
        raise AdminError(
            result.stderr.strip().replace("ERROR: ", "", 1)
            or f"Copying into {incoming} failed (exit {result.returncode})"
        )
    log.info(f"[OK] credentials are in {incoming} for {account.pw_name}")


# Command line ------------------------------------------------------------


def parser(product):
    command = f"sudo {product}-admin"
    result = arguments.Parser(
        prog=command,
        usage=(
            f"{command} <directory> [--user <account>] [--port <port>] [--verbose]\n"
            f"       {command} --credentials <directory> [--verbose]"
        ),
        description=(
            f"Install the {product} RPMs in a delivery directory and prepare this "
            "host, or with --credentials copy delivered credentials for the "
            "runtime account. Repeat the same command after a stop."
        ),
        allow_abbrev=False,
    )
    result.add_argument(
        "directory", metavar="<directory>", help="a mounted medium or a copied delivery"
    )
    result.add_argument(
        "--credentials",
        action=arguments.Once,
        default=False,
        help="copy <directory>/<component>/credentials/ into the runtime account's incoming/",
    )
    result.add_argument(
        "--user",
        metavar="<account>",
        help="the runtime account, asked if missing the first time",
    )
    result.add_argument(
        "--port",
        type=port_number,
        metavar="<port>",
        help=f"the HTTPS port, asked (default {DEFAULT_PORT}) if missing the first time",
    )
    result.add_argument(
        "--verbose", action=arguments.Once, default=False, help="also show each command"
    )
    return result


def main(command_line=None):
    product = product_name()
    command = parser(product)
    try:
        args = arguments.parse(
            command, sys.argv[1:] if command_line is None else command_line
        )
        if args.credentials and (args.user or args.port):
            command.error("--credentials takes no --user or --port")
    except arguments.UsageError as error:
        return error.code
    output.configure(verbose=args.verbose, product=product)
    if os.geteuid() != 0:
        log.error(f"ERROR: Run it as administrator: sudo {product}-admin")
        return 1
    action = f"{product}-admin {'--credentials ' if args.credentials else ''}{args.directory}"
    output.audit(action + ": started")
    try:
        if args.credentials:
            hand_over_credentials(product, Path(args.directory))
        else:
            install(product, args)
    except (AdminError, OSError, yaml.YAMLError) as error:
        log.error(f"ERROR: {error}")
        output.audit(action + ": failed")
        return 1
    output.audit(action + ": completed")
    log.info(f"PASS: {product}-admin completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
