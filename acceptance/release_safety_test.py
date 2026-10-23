#!/usr/bin/env python3
"""Separate-UID protected-release attack probes. Controller supplies code via stdin."""

import os
import pwd
import shutil
import subprocess
import sys
import tempfile
import types
from contextlib import contextmanager
from pathlib import Path

HELPER_SOURCE = ""  # RELEASE_HELPER_SOURCE

ATTACKS = """import os,sys
from pathlib import Path
assert os.getuid() != 0 and os.geteuid() != 0
root = Path(sys.argv[1])
package = root / 'deployment/common.py'
operations = (
    lambda: package.write_bytes(b'substituted package'),
    lambda: (root / 'checksums.sha256').write_text('rewritten checksums'),
    lambda: (root / 'deployment/extra.py').write_text('unlisted'),
    lambda: (root / 'deployment/link.py').symlink_to('/etc/passwd'),
    lambda: root.rename(root.with_name(root.name + '-replaced')),
    lambda: root.parent.rename(root.parent.with_name('releases-replaced')),
    lambda: root.parent.parent.rename(root.parent.parent.with_name(root.parent.parent.name + '-replaced')),
)
for operation in operations:
    try:
        operation()
    except OSError:
        continue
    raise SystemExit('FAIL: protected write unexpectedly succeeded')
print('PASS: separate-UID replacement/addition/ancestor/link attempts refused')
"""


class ProbeError(Exception):
    """Only fixed probe messages may be shown; subprocess output stays private."""


def error_message(error):
    if isinstance(error, ProbeError):
        return str(error)
    if isinstance(error, OSError):
        return "OS error errno=" + str(error.errno)
    return type(error).__name__


@contextmanager
def phase(step):
    try:
        yield
    except Exception as error:
        raise ProbeError(step + ": " + error_message(error)) from None


def run():
    if os.geteuid() != 0:
        raise ProbeError("root required")
    path, product = Path(sys.argv[1]), sys.argv[2]
    user = pwd.getpwnam(product)
    namespace = vars(types.ModuleType("trusted_release_helper"))
    exec(
        compile(HELPER_SOURCE, "controller-authenticated-release-helper", "exec"),
        namespace,
    )
    with phase("read protected inventory"):
        namespace["ancestors"](path.parent)
        before = namespace["published"](path)
    with phase("SELinux restorecon of protected release"):
        result = subprocess.run(
            ["restorecon", "-R", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=60,
        )
        if result.returncode:
            raise ProbeError("restorecon exit=" + str(result.returncode))
        if namespace["published"](path) != before:
            raise ProbeError("relabel changed release inventory")
        print("PASS: SELinux relabel preserves authenticated release bindings")
    # Must not borrow the normal deployment helper's UID or root authority.
    command = [
        "setpriv",
        "--reuid=" + str(user.pw_uid),
        "--regid=" + str(user.pw_gid),
        "--clear-groups",
        "--no-new-privs",
        "python3",
        "-B",
        "-",
        str(path),
    ]
    with phase("separate-UID write attacks"):
        result = subprocess.run(
            command,
            cwd=user.pw_dir,
            input=ATTACKS,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=30,
        )
        if result.returncode or "FAIL:" in result.stdout:
            raise ProbeError("separate-UID protection exit=" + str(result.returncode))
        print(result.stdout, end="")
        if namespace["published"](path) != before:
            raise ProbeError("published inventory changed")
    # Corrupted archive with the authentic original signature must fail BEFORE
    # extraction/enrollment; nothing from an incoming package is executed.
    root = path.parent.parent
    archive = Path(sys.argv[3])
    signature = Path(str(archive) + ".asc")
    with phase("read initial live trust"):
        trust_before = namespace["command"](["fapolicyd-cli", "--dump-db"]).stdout
    real_command = namespace["command"]

    def attempt_snapshot(snapshot):
        attack = "import sys; from pathlib import Path\ntry:\n Path(sys.argv[1]).write_bytes(b'substituted')\nexcept OSError:\n print('PASS: snapshot protected')\nelse:\n raise SystemExit(17)\n"
        result = subprocess.run(
            command[:-1] + [str(snapshot)],
            cwd=user.pw_dir,
            input=attack,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=15,
        )
        if result.returncode:
            raise ProbeError(
                "snapshot protection subprocess exit=" + str(result.returncode)
            )

    def checked_command(arguments, allowed=(0,)):
        if arguments[0] == "gpgv":
            attempt_snapshot(arguments[-1])
        result = real_command(arguments, allowed)
        if arguments[0] == "gpgv":
            attempt_snapshot(arguments[-1])
        return result

    namespace["command"] = checked_command
    with phase("authenticated repeat/snapshot protection"):
        with namespace["product_lock"](product) as locked_root:
            namespace["publish"](
                locked_root,
                archive,
                signature,
                product,
                before["component"],
                before["version"],
            )
    print("PASS: snapshot replacement before/after verification refused")
    with phase("bad signature/trust preservation"):
        with tempfile.TemporaryDirectory(
            prefix=".negative-", dir=str(root)
        ) as directory:
            bad = Path(directory) / "bad.tar.gz"
            shutil.copyfile(str(archive), str(bad))
            with bad.open("ab") as stream:
                stream.write(b"corruption")
            try:
                namespace["publish"](
                    root,
                    bad,
                    signature,
                    product,
                    before["component"],
                    before["version"],
                )
            except namespace["ReleaseError"]:
                pass
            else:
                raise ProbeError("invalid signature accepted")
        if namespace["command"](["fapolicyd-cli", "--dump-db"]).stdout != trust_before:
            raise ProbeError("negative probe changed trust")
    # Confirm service-user execution still opens the enrolled file-based package.
    with phase("service-user deploy validate"):
        result = subprocess.run(
            [
                "sudo",
                "-n",
                "-H",
                "-u",
                product,
                "bash",
                str(path / "deploy"),
                "validate",
            ],
            cwd=user.pw_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=60,
        )
        if result.returncode:
            raise ProbeError("deploy validate exit=" + str(result.returncode))
        print(
            "PASS: signature refusal left trust unchanged; protected launch validates"
        )
    with phase("host facts"):
        for arguments in (
            ["rpm", "-q", "fapolicyd", "python3", "systemd", "podman"],
            ["getenforce"],
            ["systemctl", "is-active", "fapolicyd"],
        ):
            result = subprocess.run(
                arguments,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=15,
            )
            if result.returncode:
                raise ProbeError(arguments[0] + " exit=" + str(result.returncode))
            print(result.stdout, end="")
    print("PASS: protected release probes; no outside-target writes or policy changes")


if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        raise SystemExit(
            "FAIL: protected release probe: " + error_message(error)
        ) from None
