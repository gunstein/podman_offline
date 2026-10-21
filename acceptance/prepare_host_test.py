#!/usr/bin/env python3
"""Disposable separate-UID host-path proof, or repeat preparation on lab PROD."""
# ruff: noqa: UP021, UP022
# Guest-side probe: subprocess arguments must remain compatible with Python 3.6.

import argparse
import contextlib
import grp
import json
import os
import pwd
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
from pathlib import Path

PROBE_PARENT = "/var/lib"

# Executed on stdin after the real as_service_user helper drops authority.
AUTHORITY = r"""
import json, os
from pathlib import Path
status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
keys = ("Uid", "Gid", "Groups", "CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb", "NoNewPrivs")
result = {key: status[key].strip() for key in keys}
result["SELinux"] = Path("/proc/self/attr/current").read_text().strip()
print(json.dumps(result))
"""

# Both injection points run under the service UID and operate only on fixtures.
# Execute the actual shipped helper bytes; no copy of its preparation logic.
RACE = r"""
import os, sys
from pathlib import Path
module = {"__name__": "prepare_home_probe"}
exec(compile(__HELPER_SOURCE__, sys.argv[1], "exec"), module)
home, outside, phase = Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
real_open, real_chmod = os.open, os.fchmod
calls = 0
lock = home / module["LOCK"]
if phase.startswith("lock-"):
    lock.unlink()
def swap():
    (home / ".config").rename(home / ".config-held")
    (home / ".config").symlink_to(outside)
def open_race(path, flags, *args, **kwargs):
    global calls
    if path == ".config":
        calls += 1
        if calls == 2:
            swap()
    return real_open(path, flags, *args, **kwargs)
def chmod_race(descriptor, mode):
    global calls
    if calls == 0:
        calls += 1
        swap()
    return real_chmod(descriptor, mode)
def lock_race(path, flags, *args, **kwargs):
    global calls
    if path == "cni.lock" and flags & os.O_CREAT:
        calls += 1
        if phase == "lock-link":
            lock.symlink_to(outside / "writable")
        else:
            lock.write_bytes(b"concurrent lock")
    return real_open(path, flags, *args, **kwargs)
if phase == "before-open":
    os.open = open_race
elif phase == "after-open":
    os.fchmod = chmod_race
else:
    os.open = lock_race
try:
    module["prepare"](str(home))
except (OSError, ValueError):
    if phase not in ("before-open", "lock-link"):
        raise
else:
    if phase in ("before-open", "lock-link"):
        raise RuntimeError("Unsafe replacement was accepted")
if calls == 0:
    raise RuntimeError("Replacement injection did not execute")
if phase.startswith("lock-"):
    if phase == "lock-link" and not lock.is_symlink():
        raise RuntimeError("Lock link injection did not execute")
    if phase == "lock-file" and lock.read_bytes() != b"concurrent lock":
        raise RuntimeError("Concurrent lock was truncated")
elif not (home / ".config").is_symlink():
    raise RuntimeError("Directory injection did not execute")
"""


def command(arguments, code=None, check=True, cwd=None):
    """Capture diagnostics; a failed command must never become absence/success."""
    result = subprocess.run(
        list(map(str, arguments)),
        input=code,
        cwd=None if cwd is None else str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError(
            "Host probe command failed: " + str(arguments[0]) + "\n" + result.stderr
        )
    return result


def helper_source(script):
    """The Python helper embedded in prepare-host.sh as a quoted here-document."""
    text = script.read_text()
    start = text.index("<<'PREPARE_HOME'")
    return text[text.index("\n", start) + 1 : text.index("\nPREPARE_HOME\n", start) + 1]


def shell(script, uid, gid, home, body, code=None, arguments=(), check=True):
    """Load trusted shell functions, passing every runtime parameter explicitly."""
    program = (
        """source "$1"
service_uid=$2
service_gid=$3
service_home=$4
container_home=$service_home/.local/share/containers
shift 4
"""
        + body
    )
    return command(
        [
            "bash",
            "-eu",
            "-c",
            program,
            "host-probe",
            script,
            uid,
            gid,
            home,
        ]
        + list(arguments),
        code,
        check,
    )


def as_user(script, account, home, arguments, code=None, check=True):
    return shell(
        script,
        account.pw_uid,
        account.pw_gid,
        home,
        # Root enters the home it cannot be denied; the operator's private
        # working directory is not accessible to the service user.
        'cd "$service_home"\nas_service_user env HOME="$service_home" XDG_RUNTIME_DIR="/run/user/$service_uid" "$@"',
        code=code,
        arguments=arguments,
        check=check,
    )


def check_authority(values, uid, gid):
    """All UID/GID slots and capability sets must reflect the dropped boundary."""
    if uid == 0 or gid == 0:
        raise RuntimeError("Probe requires a separate non-root account")
    if (
        values["Uid"].split() != [str(uid)] * 4
        or values["Gid"].split() != [str(gid)] * 4
    ):
        raise RuntimeError("Unexpected real/effective/saved/filesystem identity")
    if values["Groups"].strip() or values["NoNewPrivs"] != "1":
        raise RuntimeError("Supplementary groups or privilege acquisition remain")
    if any(
        int(values[key], 16)
        for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
    ):
        raise RuntimeError("Capabilities remain inside service helper")
    if len(values["SELinux"].split(":")) < 4:
        raise RuntimeError("SELinux context unavailable")


def label(path):
    return command(["stat", "-c", "%C", path]).stdout.strip()


def default_type(path):
    """Policy default type; a path without one (<<none>>) makes label checks vacuous."""
    expected = command(["matchpathcon", "-n", path]).stdout.strip().split(":")
    if len(expected) < 4:
        raise RuntimeError(
            "No SELinux default context for probe path; label checks would be vacuous: "
            + str(path)
        )
    return expected[2]


def require_default_type(path):
    """restorecon normally restores type, not the whole user/role/range context."""
    actual = label(path).split(":")
    if len(actual) < 4 or actual[2] != default_type(path):
        raise RuntimeError(
            "Service-user relabel did not restore the default type: " + str(path)
        )


def snapshot(target):
    """Disposable outside target only: ownership, permissions, bytes and labels."""
    return [
        (
            str(path.relative_to(target)),
            path.lstat().st_uid,
            path.lstat().st_gid,
            stat.S_IMODE(path.lstat().st_mode),
            label(path),
            path.read_bytes() if path.is_file() else None,
        )
        for path in [target] + sorted(target.rglob("*"))
    ]


def require_unchanged(target, before):
    if snapshot(target) != before:
        raise RuntimeError("Outside target changed (contents withheld)")


def prepare(script, account, home, check=True):
    return shell(
        script,
        account.pw_uid,
        account.pw_gid,
        home,
        "prepare_service_home\necho later-host-actions",
        check=check,
    )


@contextlib.contextmanager
def temporary_account(base):
    """Create only a uniquely named probe account; never remove a real account."""
    name = "po46-" + uuid.uuid4().hex[:12]
    home = base / "home"
    command(
        [
            "useradd",
            "--system",
            "--user-group",
            "--no-create-home",
            "--home-dir",
            home,
            "--shell",
            "/sbin/nologin",
            name,
        ]
    )
    account = None
    try:
        account = pwd.getpwnam(name)
        home.mkdir(mode=0o700)
        os.chown(str(home), account.pw_uid, account.pw_gid)
        yield account, home
    finally:
        # No --remove: do not let account metadata select a recursive deletion.
        command(["userdel", name])
        try:
            group = grp.getgrnam(name)
        except KeyError:
            pass
        else:
            if account is None or group.gr_gid != account.pw_gid:
                raise RuntimeError("Probe group identity changed; refusing cleanup")
            command(["groupdel", name])


def outside_fixture(base):
    target = base / "outside"
    target.mkdir(mode=0o755)
    (target / "sentinel").write_bytes(b"outside fixture must survive")
    # Include a non-owned but writable file. Relabeling must not rely on write
    # permission alone; intentionally wrong labels make a silent change visible.
    (target / "writable").write_bytes(b"root-owned writable fixture")
    (target / "writable").chmod(0o666)
    nested = target / "share/containers/storage"
    nested.mkdir(parents=True)
    for directory in (target, target / "share", target / "share/containers", nested):
        directory.chmod(0o755)
    (nested / "writable").write_bytes(b"root-owned nested writable fixture")
    (nested / "writable").chmod(0o666)
    # The fixture label must differ from the policy default, or a redirected
    # restorecon would leave it unchanged and the check could not see it.
    if default_type(target) == "user_home_t":
        raise RuntimeError("Outside fixture default type equals its wrong label")
    command(["chcon", "-R", "-t", "user_home_t", target])
    return target


@contextlib.contextmanager
def planted_link(script, account, home, path, target):
    """Restore the original even if planting fails after the rename succeeds."""
    held = path.with_name(path.name + "-probe-" + uuid.uuid4().hex)
    try:
        as_user(
            script,
            account,
            home,
            ["python3", "-B", "-", path, held, target],
            "import os, sys\nos.rename(sys.argv[1], sys.argv[2])\nos.symlink(sys.argv[3], sys.argv[1])\n",
        )
        yield
    finally:
        if held.exists() or held.is_symlink():
            if path.is_symlink():
                path.unlink()
            elif path.exists():
                raise RuntimeError(
                    "Unexpected probe path; original retained at " + str(held)
                )
            held.rename(path)


def disposable(script, base):
    """Exercise the actual helper, separate identities and real restorecon."""
    with temporary_account(base) as (account, home):
        authority = json.loads(
            as_user(script, account, home, ["python3", "-B", "-"], AUTHORITY).stdout
        )
        check_authority(authority, account.pw_uid, account.pw_gid)
        if authority["SELinux"] != Path("/proc/self/attr/current").read_text().strip():
            raise RuntimeError("Service helper changed the caller's SELinux context")
        print("Service helper authority: " + json.dumps(authority, sort_keys=True))
        prepare(script, account, home)
        storage = home / ".local/share/containers/storage"
        for path in (home / ".config", storage):
            wrong_type = (
                "var_t" if default_type(path) == "user_home_t" else "user_home_t"
            )
            command(["chcon", "-t", wrong_type, path])
        retained = storage / "retained-label"
        retained.write_bytes(b"retained storage fixture")
        os.chown(str(retained), account.pw_uid, account.pw_gid)
        command(["chcon", "-t", "user_home_t", retained])
        retained_label = label(retained)
        prepare(script, account, home)
        for path in (home / ".config", storage):
            require_default_type(path)
        if label(retained) != retained_label:
            raise RuntimeError("Recursive relabel entered populated storage")
        lock = home / ".config/cni/net.d/cni.lock"
        lock.write_bytes(b"retained lock")
        inode = lock.stat().st_ino
        prepare(script, account, home)
        if lock.read_bytes() != b"retained lock" or lock.stat().st_ino != inode:
            raise RuntimeError("Repeat replaced or truncated the CNI lock")
        outside = outside_fixture(base)
        before = snapshot(outside)
        for relative in (
            ".config",
            ".local",
            ".config/cni",
            ".config/cni/net.d",
            ".config/cni/net.d/cni.lock",
        ):
            path = home / relative
            for dangling in (False, True):
                with planted_link(
                    script,
                    account,
                    home,
                    path,
                    outside / "missing" if dangling else outside,
                ):
                    result = prepare(script, account, home, check=False)
                    if result.returncode == 0 or "later-host-actions" in result.stdout:
                        raise RuntimeError("Unsafe path accepted: " + relative)
                    require_unchanged(outside, before)
        foreign = home / ".config/containers"
        os.chown(str(foreign), 0, 0)
        try:
            if prepare(script, account, home, check=False).returncode == 0:
                raise RuntimeError("Foreign-owned directory accepted")
        finally:
            os.chown(str(foreign), account.pw_uid, account.pw_gid)
        for phase in ("before-open", "after-open", "lock-file", "lock-link"):
            code = RACE.replace(
                "__HELPER_SOURCE__",
                repr(helper_source(script)),
            )
            as_user(
                script,
                account,
                home,
                [
                    "python3",
                    "-B",
                    "-",
                    script,
                    home,
                    outside,
                    phase,
                ],
                code,
            )
            require_unchanged(outside, before)
            if phase.startswith("lock-"):
                lock.unlink()
                prepare(script, account, home)
            else:
                (home / ".config").unlink()
                (home / ".config-held").rename(home / ".config")
        # A replacement at the relabel command boundary is resolved under the
        # same dropped authority as recursive traversal, including writable files.
        for relative in (".local", ".local/share/containers/storage"):
            path = home / relative
            with planted_link(script, account, home, path, outside):
                as_user(
                    script,
                    account,
                    home,
                    ["restorecon", "-R", home / ".local/share/containers/storage"],
                    check=False,
                )
                as_user(script, account, home, ["restorecon", "-R", home], check=False)
                if relative == ".local":
                    as_user(
                        script,
                        account,
                        home,
                        ["restorecon", home / ".local/writable"],
                        check=False,
                    )
                require_unchanged(outside, before)
        prepare(script, account, home)
        print("PASS: separate-UID links, replacement races, lock retention and retry")


def podman(account, home, arguments):
    """Run Podman as the service user like its own session, not via as_user.

    as_service_user sets no-new-privileges, and SELinux then denies Podman's
    unconfined_t -> container_runtime_t transition (nnp_transition AVC).
    """
    return command(
        [
            "runuser",
            "-u",
            account.pw_name,
            "--",
            "env",
            "HOME=" + str(home),
            "XDG_RUNTIME_DIR=/run/user/" + str(account.pw_uid),
            "podman",
        ]
        + arguments,
        cwd=home,
    )


def product_state(script, account, home):
    """Only identifiers and volume directory labels; never inspect container env."""
    containers = podman(account, home, ["ps", "-aq", "--no-trunc"]).stdout.split()
    names = podman(account, home, ["volume", "ls", "-q"]).stdout.split()
    volumes = []
    if names:
        for item in json.loads(
            podman(account, home, ["volume", "inspect"] + names).stdout
        ):
            path = Path(item["Mountpoint"])
            volumes.append(
                (
                    item["Name"],
                    item["CreatedAt"],
                    str(path),
                    path.stat().st_ino,
                    label(path),
                )
            )
    storage = home / ".local/share/containers/storage"
    return sorted(containers), sorted(volumes), label(storage)


def installed(script, user, port, base):
    """Plant only disposable links on a resettable PROD VM, then repeat setup."""
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", user):
        raise ValueError("Invalid installed service user")
    account = pwd.getpwnam(user)
    home = Path(account.pw_dir)
    if home != Path("/var/lib") / user or account.pw_uid == 0:
        raise ValueError("Unexpected installed service home")
    outside = outside_fixture(base)
    before = snapshot(outside)
    state = product_state(script, account, home)
    # Compare populated-storage labels before/after a normal full rerun. The
    # selected mountpoint labels supplement the runner's persistent data checks.
    paths = (".config/cni", ".config/cni/net.d", ".config/cni/net.d/cni.lock")
    for relative in paths:
        path = home / relative
        with planted_link(
            script,
            account,
            home,
            path,
            outside / "missing" if relative.endswith("cni.lock") else outside,
        ):
            result = command(
                ["bash", script, "--port", port, "--user", user], check=False
            )
            if (
                result.returncode == 0
                or "Service-home preparation failed" not in result.stderr
            ):
                raise RuntimeError(
                    "Full preparation did not refuse planted link: " + relative
                )
            require_unchanged(outside, before)
    command(["bash", script, "--port", port, "--user", user])
    if product_state(script, account, home) != state:
        raise RuntimeError(
            "Normal repeat changed container/volume identity or storage labels"
        )
    print(
        "PASS: installed malicious paths refused; normal repeat preserved runtime state"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path)
    parser.add_argument("--installed-user")
    parser.add_argument("--port", type=int, default=8443)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run as root on a disposable SELinux Enforcing lab VM")
    if command(["getenforce"]).stdout.strip() != "Enforcing":
        parser.error("SELinux Enforcing is required; this is not a mocked label test")
    script = args.script.resolve(strict=True)
    # Like the real service home, the fixture lives under /var/lib: the policy
    # maps /var/tmp/.* to <<none>>, so restorecon would never change a label
    # there and every relabel check would pass vacuously. The caller explicitly
    # chooses a disposable lab; never run against arbitrary hosts.
    with tempfile.TemporaryDirectory(
        prefix="podman-offline-host-", dir=PROBE_PARENT
    ) as directory:
        base = Path(directory)
        base.chmod(0o755)
        if args.installed_user:
            installed(script, args.installed_user, args.port, base)
        else:
            stage = base / "scripts"
            stage.mkdir()
            shutil.copyfile(str(script), str(stage / "prepare-host.sh"))
            disposable(stage / "prepare-host.sh", base)


if __name__ == "__main__":
    main()
