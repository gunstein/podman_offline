"""Fresh-process real setup orchestration; only OS identity/host commands are simulated."""

import importlib.util
import json
import os
import signal
import sys
import types
from pathlib import Path
from typing import Any

SPEC = importlib.util.spec_from_file_location(
    "host_release", Path(__file__).resolve().parents[2] / "scripts/release.py"
)
assert SPEC is not None and SPEC.loader is not None
release: Any = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
root = Path(sys.argv[1])
failure = sys.argv[2]
release.OWNER = os.getuid()
release.BASE = root / "lib"
release.TMP = root / "tmp"
release.JOURNAL = root / "log/journal"
release.SYSTEMD = root / "systemd"
release.FAPOLICYD = root / "fapolicyd.conf"
release.OS_RELEASE = root / "os-release"
release.RESERVE = 4096


def ancestors(path):
    path.relative_to(root)
    for item in (path,) + tuple(path.parents):
        if item == root:
            break
        release.protected(item, directory=True)


release.ancestors = ancestors
release.pwd.getpwnam = lambda name: types.SimpleNamespace(
    pw_uid=os.getuid(),
    pw_gid=os.getgid(),
    pw_dir=str(root / "home"),
    pw_shell="/bin/bash",
)
real_command = release.command


def command(args, allowed=(0,)):
    with (root / "calls.jsonl").open("a") as stream:
        stream.write(json.dumps(args) + "\n")
    stdout, code = "", 0
    if args[0] == "gpgv":
        if failure == "kill-signature":
            os.kill(os.getpid(), signal.SIGKILL)
        return real_command(args, allowed)
    if args[0] == "id":
        stdout = "operator-a\n"
    elif args[0] == "sudo":
        stdout, code = "User operator-a is not allowed to run sudo on fixture.\n", 0
    elif args[0] == "getenforce":
        stdout = "Enforcing\n"
    elif args[:2] == ["systemctl", "is-active"]:
        stdout = "active\n"
    elif args[0] == "systemd-analyze":
        stdout = (root / "journald.conf").read_text()
    elif args[0] == "journalctl":
        if failure == "flush":
            raise release.CommandError("journalctl", 1)
        machine = release.JOURNAL / "machine"
        machine.mkdir(exist_ok=True)
        (machine / "system.journal").touch()
    elif args[0] == "systemd-tmpfiles" and failure == "kill-journal":
        os.kill(os.getpid(), signal.SIGKILL)
    elif args[:2] == ["fapolicyd-cli", "--update"] and failure == "trust":
        raise release.CommandError("fapolicyd-cli", 1)
    elif args[:2] == ["fapolicyd-cli", "--dump-db"]:
        stdout = "\n".join(
            "file " + line
            for path in release.TRUST_DIR.iterdir()
            for line in path.read_text().splitlines()
            if line and not line.startswith("#")
        )
    elif args[0] == "/usr/bin/bash":
        if failure == "host":
            raise release.CommandError("bash", 1)
        for name in ("state", "config", "storage"):
            (release.BASE / "cedar" / name).mkdir(mode=0o700, exist_ok=True)
        (root / "manager-ready").touch()
    elif args[0] == "loginctl":
        stdout = "yes\n" if (root / "manager-ready").exists() else "no\n"
    elif args[:2] == ["systemctl", "--user"]:
        stdout = (
            "XDG_CONFIG_HOME="
            + str(release.BASE / "cedar/config")
            + "\nXDG_DATA_HOME="
            + str(release.BASE / "cedar/storage")
            + "\n"
        )
    result = types.SimpleNamespace(stdout=stdout, stderr="", returncode=code)
    if code not in allowed:
        raise release.CommandError(args[0], code)
    return result


release.command = command
release.shutil.which = lambda name: (
    None if failure == "missing-tools" and name == "semanage" else "/usr/bin/" + name
)
release.TRUST_DIR = root / "trust"
args = types.SimpleNamespace(
    product="cedar",
    user="operator-a",
    port=8443,
    input_dir=root / "upload",
    keyring=root / "upload/keyring.gpg",
    key_sha256=release.input_digest(root / "upload/keyring.gpg"),
    release=["worker@1.0.0", "processor@2.3.4"],
    host_release="worker@1.0.0",
    component=None,
    version=None,
    archive=None,
    signature=None,
    old_version=None,
)
try:
    release.setup_host(args, release.setup_request(args))
except release.ReleaseError as error:
    print(release.error_message(error))
    raise SystemExit(1)
