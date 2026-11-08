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
8. Retirement (decision 3): remove an older release once the runtime account
   has completed a newer version of its component and has no unfinished
   installation of it. The newest release's own deploy.sh status --json,
   run as the account, says so; root reads only that bounded JSON. Each
   release is removed in its own dnf transaction, allowed by a single-use
   authorization the package's erase guard reads (rpms.py).

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
import select as io_select
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import typing
from pathlib import Path

import host
import yaml
from host import (
    QUERY,
    RELEASE_PATH,
    Package,
    ToolError,
    ask,
    component_of,
    configured_port,
    host_conf,
    installed,
    newest_releases,
    prepared_account,
    product_name,
    run,
    version_key,
)

from deployment import arguments, output

log = output.log

# Host paths; tests point them at temporary files.
JOURNAL = Path("/var/log/journal")
RUN = Path("/run")
OS_RELEASE = Path("/etc/os-release")
FAPOLICYD_CONF = Path("/etc/fapolicyd/fapolicyd.conf")

DEFAULT_PORT = 8443
TRUST_WAIT = 30  # seconds for fapolicyd to learn about newly installed files
REPORT_LIMIT = 64 * 1024  # bytes read from a command run as the runtime account
STATUS_WAIT = 120  # seconds for deploy.sh status --json as the runtime account
CREDENTIAL_LIMIT = 1024 * 1024  # bytes per credential file
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


def run_release(account, release, *arguments):
    """deploy.sh of an installed release as the account, in a cleared environment."""
    return as_account(account) + [
        "env",
        "-i",
        f"HOME={account.pw_dir}",
        "PATH=/usr/bin:/bin",
        "LANG=C.UTF-8",
        "bash",
        str(release / "deploy.sh"),
        *arguments,
    ]


def run_bounded(command, seconds, limit=REPORT_LIMIT):
    """Run a command as the runtime account with a time limit and an output cap.

    Its output is not trusted: a child that hangs or floods stdout/stderr
    must not stall or exhaust the root command. The command runs in its own
    session; on either limit its whole process group is killed and reaped,
    and the result's returncode is None.
    """
    log.debug("+ " + " ".join(command))
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=dict(os.environ, LC_ALL="C"),
        start_new_session=True,
    )
    out, err = process.stdout, process.stderr
    assert out is not None and err is not None
    chunks = {out: [], err: []}
    reading = [out, err]
    deadline = time.monotonic() + seconds
    size, exceeded, status = 0, False, None
    try:
        while reading and not exceeded:
            left = deadline - time.monotonic()
            ready = io_select.select(reading, [], [], left)[0] if left > 0 else []
            if not ready:
                exceeded = True
            for stream in ready:
                data = os.read(stream.fileno(), 65536)
                if not data:
                    reading.remove(stream)
                chunks[stream].append(data)
                size += len(data)
                exceeded = exceeded or size > limit
        if not exceeded:
            try:
                status = process.wait(max(deadline - time.monotonic(), 0))
            except subprocess.TimeoutExpired:
                pass
    finally:
        # Also on an exception (Ctrl+C): the group is in its own session and
        # would outlive this command. It may be gone already.
        try:
            if status is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        finally:
            out.close()
            err.close()
    text = {s: b"".join(c).decode(errors="replace") for s, c in chunks.items()}
    # returncode None means a limit was reached (callers check for 0 or 1).
    return subprocess.CompletedProcess(
        command, typing.cast(int, status), text[out], text[err]
    )


def last_line(result):
    detail = (result.stderr or "").strip().splitlines()
    return detail[-1] if detail else ""


# Answers -----------------------------------------------------------------


def port_number(value):
    """argparse type: an unprivileged TCP port."""
    if not value.isdigit() or not 1024 <= int(value) <= 65535:
        raise ValueError(value)
    return int(value)


def answers(product, args):
    """The runtime account and HTTPS port: from the host once prepared, else asked.

    The owner of state/ is the account (prepare-host.sh creates it) and
    host.conf the port; neither is changed after the first preparation.
    """
    prepared = prepared_account(product)
    account = prepared.pw_name if prepared else None
    if account and args.user and args.user != account:
        raise ToolError(
            f"{product} runs as {account} on this host; another account is not supported"
        )
    account = (
        account
        or args.user
        or ask(
            "Runtime account (an existing login account without sudo)", None, "--user"
        )
    )
    port = configured_port(product)
    if port and args.port and args.port != port:
        raise ToolError(
            f"{product} uses HTTPS port {port} on this host; changing it is not supported"
        )
    if not port and not args.port:
        try:
            args.port = port_number(ask("HTTPS port", str(DEFAULT_PORT), "--port"))
        except ValueError:
            raise ToolError("The HTTPS port must be a number 1024-65535") from None
    return account, port or args.port


# Preflight ---------------------------------------------------------------


def check_os():
    text = OS_RELEASE.read_text()
    if not (
        re.search(r"^ID=[\"']?ol[\"']?$", text, re.MULTILINE)
        and re.search(r"^VERSION_ID=[\"']?9(\.[0-9]+)?[\"']?$", text, re.MULTILINE)
    ):
        raise ToolError("This host is not Oracle Linux 9; use a supported host")


def check_selinux():
    mode = run(["getenforce"]).stdout.strip()
    if mode != "Enforcing":
        raise ToolError(
            f"SELinux is {mode}; the system administrator sets it to Enforcing"
        )


def check_services():
    for service in ("firewalld", "fapolicyd"):
        state = run(["systemctl", "is-active", service], check=False).stdout.strip()
        if state != "active":
            raise ToolError(
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
        raise ToolError(
            f"fapolicyd does not trust the RPM database (trust = {settings['trust']} "
            f"in {FAPOLICYD_CONF}); the security administrator adds rpmdb"
        )
    cache = settings.get("subj_cache_size", "")
    if not cache.isdigit() or int(cache) < 16381:
        raise ToolError(
            f"Set subj_cache_size = 16381 in {FAPOLICYD_CONF} and restart fapolicyd "
            "(security administrator); a smaller cache denies Podman at start"
        )
    if run(["rpm", "-q", "rpm-plugin-fapolicyd"], check=False).returncode != 0:
        raise ToolError(
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
        raise ToolError(
            f"journald has Storage={values['Storage']}; the system administrator "
            "allows persistent journals (Storage=auto or persistent)"
        )
    if values["SplitMode"] != "uid":
        raise ToolError(
            f"journald has SplitMode={values['SplitMode']}; "
            "the system administrator sets SplitMode=uid"
        )


def check_account(name):
    """An ordinary login account without sudo rights or privileged groups."""
    try:
        account = pwd.getpwnam(name)
    except KeyError:
        raise ToolError(
            f"Account {name} does not exist; create it with the organisation's "
            "normal procedure first"
        ) from None
    if account.pw_uid < 1000 or 61184 <= account.pw_uid <= 65535 or account.pw_gid == 0:
        raise ToolError(
            f"{name} has UID {account.pw_uid}; use an ordinary login account (UID 1000 or higher)"
        )
    if account.pw_shell.endswith(("/nologin", "/false")):
        raise ToolError(
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
        raise ToolError(
            f"{name} is in the privileged group(s) {', '.join(privileged)}; "
            "use an account without them"
        )
    result = run(["sudo", "-n", "-l", "-U", name], check=False)
    # Only the complete denial proves no grants; OL9 may exit 0 either way.
    denial = r"User " + re.escape(name) + r" is not allowed to run sudo on [^\n]+\."
    if not re.fullmatch(denial, (result.stdout + result.stderr).strip()):
        raise ToolError(
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
        raise ToolError(
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
        except (ToolError, OSError) as error:
            errors.append(str(error))
    if errors:
        raise ToolError(
            "Preflight stopped before any change:\n- " + "\n- ".join(errors)
        )
    log.info("[OK] preflight")


# Packages ----------------------------------------------------------------


def copy_regular(source, target):
    """Copy a regular file without following a link or opening a device."""
    try:
        descriptor = os.open(str(source), FILE_FLAGS)
    except OSError as error:
        raise ToolError(
            f"Cannot read {source} ({error.strerror}); deliver regular files"
        ) from None
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ToolError(f"{source} is not a regular file; deliver regular files")
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
                raise ToolError(
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
            raise ToolError(
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
        raise ToolError(
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
    script = host.TOOLS / "scripts/prepare-host.sh"
    command = ["bash", str(script), "--port", str(port), "--user", account.pw_name]
    if run(command, check=False, capture=False).returncode != 0:
        raise ToolError(
            f"Host preparation stopped; fix what it names, then run sudo {product}-admin again"
        )
    # The one source of the port for the runtime command; public, root-owned.
    directory = host.ETC / product
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
    newest = newest_releases(packages)
    if not newest:
        log.warning(
            f"WARNING: no {product} release is installed yet; deliver the release RPMs"
        )
    for _, package in sorted(newest.items()):
        release = Path(RELEASE_PATH.format(product=product, name=package.name))
        command = run_release(account, release, "--help")
        deadline = time.monotonic() + TRUST_WAIT
        while True:
            result = run_bounded(command, TRUST_WAIT)
            if result.returncode == 0:
                break
            if time.monotonic() >= deadline:
                detail = last_line(result)
                raise ToolError(
                    f"{account.pw_name} cannot run {release}/deploy.sh"
                    + (f" ({detail})" if detail else "")
                    + "; fapolicyd must trust RPM-installed files: the security "
                    "administrator checks fapolicyd-cli --list and the audit log, "
                    f"then run sudo {product}-admin again"
                )
            time.sleep(1)
        log.info(f"[OK] {account.pw_name} can run {package.name}")


# Retirement --------------------------------------------------------------


def runtime_report(product, account, release):
    """{component: (completed version, recorded version)} and the pending component.

    From the release's own deploy.sh status --json as the account: it reads
    the installed markers, installed metadata and pending record (and refuses
    links or invalid markers), so root never opens the account's files. The
    JSON comes from the account and is checked before any decision; it is the
    account's report, not proof, so the newest release is never removed
    whatever it says. Exit 1 only says that a unit is not active, which
    retirement ignores; anything else, a time limit or too much output keeps
    every release.
    """
    result = run_bounded(run_release(account, release, "status", "--json"), STATUS_WAIT)
    try:
        if result.returncode not in (0, 1):
            raise ValueError("no complete status run")
        report = json.loads(result.stdout)
        if report["product"] != product or not isinstance(report["components"], list):
            raise ValueError("another product or no component list")
        versions = {}
        for item in report["components"]:
            name, completed, recorded = (
                item["name"], item["version"], item["recorded_version"],
            )  # fmt: skip
            if not (
                isinstance(name, str)
                and host.ID.fullmatch(name)
                and name not in versions
                and (completed is None or host.VERSION.fullmatch(completed))
                and host.VERSION.fullmatch(recorded)
            ):
                raise ValueError("invalid component")
            versions[name] = (completed, recorded)
        pending = report["pending"]
        if pending is not None and not (
            isinstance(pending, dict)
            and pending.get("operation") in ("install", "uninstall")
            and isinstance(pending.get("component"), str)
            and host.ID.fullmatch(pending["component"])
            and isinstance(pending.get("owners"), list)
            and all(
                isinstance(o, str) and host.ID.fullmatch(o) for o in pending["owners"]
            )
            # As registrations.load_pending: unique owners, not the component.
            and len(set(pending["owners"])) == len(pending["owners"])
            and pending["component"] not in pending["owners"]
        ):
            raise ValueError("invalid pending record")
    except (ValueError, TypeError, KeyError, RecursionError):
        detail = last_line(result) or "no valid status --json output"
        raise ToolError(
            f"the installation state of {account.pw_name} could not be read ({detail})"
        ) from None
    return versions, pending and pending["component"]


def keep_reason(package, versions, pending):
    """Why an older release stays, or None when it may be removed (decision 3)."""
    component = package.component
    if component == pending:
        return f"an installation of {component} is unfinished"
    completed, recorded = versions.get(component, (None, None))
    if completed is None:
        return f"{component} is not installed"
    for version in (completed, recorded):
        if package.version == version:
            return f"{component} {version} is the installed version"
        if version_key(package.version) > version_key(version):
            return f"it is newer than the installed {component} {version}"
    return None


def remove(product, package):
    """Remove one release package: authorize exactly it, dnf, then check the result.

    The authorization is the package's name-version-release with this
    process's PID and start time, in a root-only file under /run. The
    package's %preun allows the erase only for that content while this
    process is alive, and deletes it (rpms.GUARD); this command deletes it
    too when dnf returns. A killed command therefore leaves nothing a later
    plain erase could use. After an interruption the package is either gone
    or still installed; a repeat checks it again and removes it, also with
    files already missing, and a tree left without its package stops every
    later run (retire).
    """
    others = {p.name for p in installed(product)} - {package.name}
    identity = run(
        ["rpm", "-q", "--queryformat", "%{NAME}-%{VERSION}-%{RELEASE}", package.name]
    ).stdout.strip()
    record = RUN / product / "erase-authorization"
    record.parent.mkdir(mode=0o700, exist_ok=True)
    partial = record.with_name(record.name + ".partial")
    # Field 22 of /proc/<pid>/stat, the start time: a reused PID differs.
    started = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19]
    partial.write_text(f"{identity} {os.getpid()} {started}\n")
    os.replace(str(partial), str(record))
    try:
        result = run(DNF + ["remove", package.name], check=False)
    finally:
        try:
            record.unlink()
        except FileNotFoundError:
            pass
    if result.returncode != 0:
        detail = last_line(result)
        raise ToolError(
            f"dnf remove {package.name} failed (exit {result.returncode})"
            + (f": {detail}" if detail else "")
            + f"; run sudo {product}-admin again"
        )
    left = {p.name for p in installed(product)}
    if package.name in left:
        raise ToolError(
            f"{package.name} is still installed after dnf remove; run sudo "
            f"{product}-admin again"
        )
    if left != others:
        raise ToolError(
            f"dnf remove {package.name} also removed {', '.join(sorted(others - left))}; "
            f"deliver them again with sudo {product}-admin <delivery directory>"
        )
    tree = host.release_path(product, package)
    if tree.exists() or tree.is_symlink():
        raise ToolError(
            f"{tree} is left after removing {package.name}: no package owns its "
            "files. Ask the supplier before deleting anything"
        )


def retire(product, account):
    """Step 8: remove the releases the runtime account no longer needs."""
    packages = installed(product)
    # A tree without its package (files left by a removal, or a removal
    # interrupted before its check) stops every run until someone inspects it.
    owned = {package.name for package in packages if package.component}
    releases = host.LIB / product / "releases"
    for tree in sorted(releases.iterdir()) if releases.is_dir() else ():
        if tree.name not in owned:
            raise ToolError(
                f"{tree} has no installed release package: no package owns its files. "
                "Ask the supplier before deleting anything"
            )
    newest = newest_releases(packages)
    older = sorted(
        (p for p in packages if p.component and p != newest[p.component]),
        key=lambda p: (p.component, version_key(p.version)),
    )
    if not older:
        return
    release = Path(
        RELEASE_PATH.format(product=product, name=newest[older[0].component].name)
    )
    try:
        versions, pending = runtime_report(product, account, release)
    except ToolError as error:
        log.warning(
            f"WARNING: older releases kept ({', '.join(p.name for p in older)}): "
            f"{error}; a later sudo {product}-admin removes them once "
            f"{account.pw_name} has run {product}"
        )
        return
    for package in older:
        reason = keep_reason(package, versions, pending)
        if reason:
            log.info(f"[OK] {package.name} kept: {reason}")
        else:
            remove(product, package)
            log.info(
                f"[OK] removed {package.name}, which {account.pw_name} no longer uses"
            )


def install(product, args):
    account_name, port = answers(product, args)
    preflight(account_name)
    account = pwd.getpwnam(account_name)
    install_packages(product, args, account_name, port)
    prepare_host(product, account, port)
    check_trust(product, account, installed(product))
    retire(product, account)
    log.info(
        f"[OK] next: log in as {account_name} (at the console, or ssh "
        f"{account_name}@<server>) and run {product}"
    )


# Credentials -------------------------------------------------------------


def read_file(parent, name, path):
    try:
        descriptor = os.open(name, FILE_FLAGS, dir_fd=parent)
    except OSError as error:
        raise ToolError(f"Cannot read {path} ({error.strerror})") from None
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ToolError(f"{path} is not a regular file; deliver regular files only")
        if info.st_size > CREDENTIAL_LIMIT:
            raise ToolError(
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
                raise ToolError(
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
                    raise ToolError(
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
    incoming = host.LIB / product / "incoming"
    account = prepared_account(product)
    if account is None or account.pw_uid == 0 or not incoming.is_dir():
        raise ToolError(
            f"{incoming} is not prepared; first run sudo {product}-admin <delivery directory>"
        )
    components = {package.component for package in installed(product)}
    files = read_credentials(product, directory, components - {""})
    if not files:
        raise ToolError(
            f'No <component>/credentials/ directory in {directory}; see "Before you begin" in the manual for the layout'
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
        raise ToolError(
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
    except (ToolError, OSError, yaml.YAMLError) as error:
        log.error(f"ERROR: {error}")
        output.audit(action + ": failed")
        return 1
    output.audit(action + ": completed")
    log.info(f"PASS: {product}-admin completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
