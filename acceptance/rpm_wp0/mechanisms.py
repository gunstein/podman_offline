"""Minimal WP0 D/F/G/H mechanism probes. Never a product implementation."""

import array
import fcntl
import json
import os
import pwd
import secrets
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path

from contracts import ACCOUNT, LOCK_TIMEOUT, bounded_poll, require
from operations import command, dnf, rpm_clean, versions

STATE = Path("/var/lib/wp0-probe/state")
RELEASES = Path("/var/lib/wp0-probe/releases")
IDENTITIES = Path("/var/lib/wp0-probe/identities")
RUN = Path("/run/wp0-probe")
SOURCE = "/usr/libexec/wp0/mechanisms.py"
ADMIN = "/usr/bin/wp0-admin"


def acquire(fd, timeout=LOCK_TIMEOUT, clock=time.monotonic, sleep=time.sleep):
    start = clock()
    while True:
        require(
            clock() - start <= timeout, "STOP: operation lock busy (5 second limit)"
        )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if clock() - start > timeout:
                fcntl.flock(fd, fcntl.LOCK_UN)
                raise RuntimeError("STOP: operation lock acquired after deadline")
            return True
        except BlockingIOError:
            require(
                clock() - start < timeout, "STOP: operation lock busy (5 second limit)"
            )
            sleep(min(0.05, max(0, timeout - (clock() - start))))


def inherited(fd, path):
    """An unlocked descriptor for the same inode is a forgery too."""
    received, expected = os.fstat(fd), path.lstat()
    require(stat.S_ISREG(expected.st_mode), "STOP: forged operation lock path")
    require(
        (received.st_dev, received.st_ino) == (expected.st_dev, expected.st_ino),
        "STOP: forged operation lock descriptor",
    )
    other = os.open(str(path), os.O_RDWR | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        raise RuntimeError("STOP: descriptor did not inherit an existing lock")
    finally:
        os.close(other)


def receive_lock(sock):
    message, controls, flags, _ = sock.recvmsg(
        8192, socket.CMSG_SPACE(array.array("i").itemsize)
    )
    require(not flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC), "Truncated lock reply")
    descriptors = array.array("i")
    for level, kind, data in controls:
        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
            descriptors.frombytes(data[: len(data) - len(data) % descriptors.itemsize])
    try:
        require(len(descriptors) == 1, "Expected exactly one lock descriptor")
        reply = json.loads(message)
        require(
            reply == {"state": "uninitialized", "allowed": True},
            "Invalid retire-check reply",
        )
        return descriptors[0]
    except BaseException:
        for fd in descriptors:
            os.close(fd)
        raise


def check_child(channel):
    # This minimal fixture models the uninitialized row only; product state is
    # never read by root. F/G test guard/transport, not the later retire planner.
    require(
        not any(p.name != ".operation.lock" for p in STATE.iterdir()),
        "Probe state is not uninitialized",
    )
    fd = os.open(
        str(STATE / ".operation.lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    acquire(fd)
    with socket.socket(fileno=channel) as sock:
        sock.sendmsg(
            [json.dumps({"state": "uninitialized", "allowed": True}).encode()],
            [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))],
        )
    os.close(fd)


def dropped(*arguments):
    account = pwd.getpwnam(ACCOUNT)
    return [
        "setpriv",
        "--reuid=" + str(account.pw_uid),
        "--regid=" + str(account.pw_gid),
        "--clear-groups",
        "--inh-caps=-all",
        "--ambient-caps=-all",
        "--bounding-set=-all",
        "--no-new-privs",
        "env",
        "-i",
        "HOME=" + account.pw_dir,
        "USER=" + ACCOUNT,
        "LOGNAME=" + ACCOUNT,
        "PATH=/usr/bin:/bin",
        *arguments,
    ]


def locked_check():
    parent, child = socket.socketpair()
    try:
        process = subprocess.Popen(
            dropped("python3", "-B", SOURCE, "check", str(child.fileno())),
            pass_fds=(child.fileno(),),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        child.close()
        parent.settimeout(LOCK_TIMEOUT + 2)
        fd = receive_lock(parent)
        out, err = process.communicate(timeout=LOCK_TIMEOUT + 2)
        require(
            process.returncode == 0 and not out and not err, "Retire-check child failed"
        )
        return fd
    finally:
        parent.close()
        child.close()


def proc_stat(pid):
    # comm may contain spaces and parentheses; split after its final closing paren.
    fields = Path("/proc", str(pid), "stat").read_text().rsplit(")", 1)[1].split()
    return int(fields[1]), fields[19]


def guard_record(record, package, ancestors, boot, read_process):
    require(
        record.get("package") == package,
        "STOP: erase authorization names another package",
    )
    require(record.get("boot") == boot, "STOP: erase authorization names another boot")
    pid = record.get("pid")
    require(isinstance(pid, int) and pid > 1, "STOP: invalid authorization PID")
    try:
        start, is_admin = read_process(pid)
    except (OSError, ValueError):
        raise RuntimeError("STOP: erase authorization PID is dead") from None
    require(start == record.get("start"), "STOP: erase authorization PID was reused")
    require(is_admin, "STOP: authorization process is not wp0-admin")
    require(pid in ancestors, "STOP: authorization process is not an ancestor")
    require(
        isinstance(record.get("nonce"), str) and len(record["nonce"]) == 64,
        "STOP: invalid authorization nonce",
    )
    return True


def guard(package, kind, count):
    # RPM passes remaining instances, including duplicate cleanup and upgrade.
    if count > 0:
        return True
    require(kind != "tools", "STOP: use sudo wp0-admin; tools erase refused")
    path = RUN / "erase-authorization"
    require(
        path.is_file()
        and path.stat().st_uid == 0
        and path.stat().st_mode & 0o777 == 0o600,
        "STOP: use sudo wp0-admin; no private authorization",
    )
    ancestors = []
    pid = os.getpid()
    while pid > 1:
        pid, _ = proc_stat(pid)
        ancestors.append(pid)

    def read_process(process):
        args = Path("/proc", str(process), "cmdline").read_bytes().split(b"\0")
        root = Path("/proc", str(process)).stat().st_uid == 0
        return proc_stat(process)[1], root and ADMIN.encode() in args

    guard_record(
        json.loads(path.read_text()),
        package,
        ancestors,
        Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        read_process,
    )
    (RUN / "approved").write_text(package)
    if (RUN / "pause-erase").exists():
        bounded_poll(lambda remaining: (RUN / "continue-erase").exists(), 60)
    return True


def package_identity(package):
    # A canonical header projection, including every field named by the plan.
    format_string = "%{NAME}\\n%{VERSION}\\n%{RELEASE}\\n[%{FILENAMES}\\t%{FILEMODES}\\t%{FILEUSERNAME}\\t%{FILEGROUPNAME}\\t%{FILESIZES}\\t%{FILEDIGESTS}\\n]"
    header = command(["rpm", "-q", "--qf", format_string, package]).stdout
    projections = {}
    for label, option in (
        ("scripts", "--scripts"),
        ("requires", "--requires"),
        ("provides", "--provides"),
        ("conflicts", "--conflicts"),
    ):
        value = command(["rpm", "-q", option, package]).stdout
        projections[label] = value if label == "scripts" else sorted(value.splitlines())
    return {"header": header, **projections}


def record_identity(package):
    IDENTITIES.mkdir(mode=0o755, parents=True, exist_ok=True)
    require(
        not IDENTITIES.is_symlink() and IDENTITIES.stat().st_uid == 0,
        "Identity directory must be root-owned",
    )
    IDENTITIES.chmod(0o755)
    target = IDENTITIES / (package + ".json")
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(package_identity(package), sort_keys=True))
    temporary.chmod(0o644)
    temporary.replace(target)


def verify_identity(package):
    target = IDENTITIES / (package + ".json")
    require(
        target.is_file()
        and not target.is_symlink()
        and target.stat().st_uid == 0
        and stat.S_IMODE(target.stat().st_mode) == 0o644,
        "STOP: missing identity record",
    )
    require(
        json.loads(target.read_text()) == package_identity(package),
        "STOP: mismatching identity record",
    )
    require(rpm_clean(package), "STOP: installed package damaged")
    root = RELEASES / package
    checksums = root / "checksums.sha256"
    command(["sha256sum", "-c", checksums], cwd=str(root))
    return True


def runtime(inherited_fd=None):
    path = STATE / ".operation.lock"
    if inherited_fd is not None:
        inherited(inherited_fd, path)
    else:
        fd = os.open(str(path), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            acquire(fd)
        finally:
            os.close(fd)
    return True


def erase(package, fault="none", hold=False):
    require(
        package in ("wp0-release-base", "wp0-release-sibling"),
        "Only probe release packages may be erased",
    )
    require(
        fault in ("none", "package", "boot", "dead", "reused"), "Unknown erase fault"
    )
    RUN.mkdir(mode=0o700, exist_ok=True)
    admin_lock = os.open(str(RUN / "admin.lock"), os.O_CREAT | os.O_RDWR, 0o600)
    acquire(admin_lock)
    fd = locked_check()
    nvr = command(
        ["rpm", "-q", "--qf", "%{NAME}-%{VERSION}-%{RELEASE}", package]
    ).stdout
    others = command(
        ["rpm", "-qa", "wp0-release*", "--qf", "%{NAME}\\n"]
    ).stdout.splitlines()
    record = {
        "package": nvr,
        "pid": os.getpid(),
        "start": proc_stat(os.getpid())[1],
        "boot": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "nonce": secrets.token_hex(32),
    }
    if fault == "package":
        record["package"] = "another-package-1-1"
    if fault == "boot":
        record["boot"] = "another-boot"
    if fault == "dead":
        record["pid"] = 2147483647
    if fault == "reused":
        record["start"] = "0"
    authorization = RUN / "erase-authorization"
    authorization.write_text(json.dumps(record))
    authorization.chmod(0o600)
    try:
        if hold:
            (RUN / "holding").write_text("ready")
            bounded_poll(lambda remaining: (RUN / "release-hold").exists(), 60)
            return True
        # The supervisor retains the same descriptor and records the dnf result
        # if this admin is killed after preun approval. dnf itself inherits fd too.
        child = subprocess.Popen(
            ["python3", "-B", SOURCE, "transaction", package, str(fd)], pass_fds=(fd,)
        )
        (RUN / "transaction-pid").write_text(str(child.pid))
        require(child.wait(timeout=120) == 0, "Erase transaction failed")
        require(
            not versions(package) and not (RELEASES / package).exists(),
            "Erase postcondition failed",
        )
        for other in others:
            if other != package:
                require(
                    bool(versions(other)) and rpm_clean(other),
                    "Sibling release changed",
                )
        (IDENTITIES / (package + ".json")).unlink(missing_ok=True)
        return True
    finally:
        authorization.unlink(missing_ok=True)
        os.close(fd)
        os.close(admin_lock)


def main():
    mode, *args = sys.argv[1:]
    if mode == "check":
        check_child(int(args[0]))
        return
    elif mode == "guard":
        guard(args[0], args[1], int(args[2]))
    elif mode == "runtime":
        runtime(int(args[0]) if args else None)
    elif mode == "erase":
        erase(args[0], args[1] if len(args) > 1 else "none")
    elif mode == "hold":
        erase(args[0], hold=True)
    elif mode == "verify":
        verify_identity(args[0])
    elif mode == "use":
        verify_identity(args[0])
        command(["bash", RELEASES / args[0] / "deploy.sh", "init-layout"])
    elif mode == "transaction":
        fd = int(args[1])
        result = dnf("remove", args[0], pass_fds=(fd,), allowed=tuple(range(256)))
        temporary = RUN / "transaction-result.tmp"
        temporary.write_text(
            json.dumps(
                {
                    "exit": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
        )
        temporary.replace(RUN / "transaction-result")
        require(result.returncode == 0, "dnf erase failed")
    else:
        raise RuntimeError("Unknown WP0 mechanism command")
    print("WP0 mechanism completed", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(3) from None
