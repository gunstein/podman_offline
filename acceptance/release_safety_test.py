#!/usr/bin/env python3
"""Separate-UID protected-release attack probes. Controller supplies code via stdin."""

import os
import pwd
import shutil
import subprocess
import sys
import tempfile
import types
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


def run():
    if os.geteuid() != 0:
        raise RuntimeError("root required")
    path, product = Path(sys.argv[1]), sys.argv[2]
    user = pwd.getpwnam(product)
    namespace = vars(types.ModuleType("trusted_release_helper"))
    exec(
        compile(HELPER_SOURCE, "controller-authenticated-release-helper", "exec"),
        namespace,
    )
    namespace["ancestors"](path.parent)
    before = namespace["published"](path)
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
        raise RuntimeError("separate-UID protection failed")
    print(result.stdout, end="")
    if namespace["published"](path) != before:
        raise RuntimeError("published inventory changed")
    # Corrupted archive with the authentic original signature must fail BEFORE
    # extraction/enrollment; nothing from an incoming package is executed.
    root = path.parent.parent
    archive = Path(sys.argv[3])
    signature = Path(str(archive) + ".asc")
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
            raise RuntimeError("snapshot writable by service user")

    def checked_command(arguments, allowed=(0,)):
        if arguments[0] == "gpgv":
            attempt_snapshot(arguments[-1])
        result = real_command(arguments, allowed)
        if arguments[0] == "gpgv":
            attempt_snapshot(arguments[-1])
        return result

    namespace["command"] = checked_command
    with namespace["product_lock"](product) as locked_root:
        namespace["publish"](
            locked_root,
            archive,
            signature,
            root / "keyring.gpg",
            product,
            before["component"],
            before["version"],
        )
    print("PASS: snapshot replacement before/after verification refused")
    with tempfile.TemporaryDirectory(prefix=".negative-", dir=str(root)) as directory:
        bad = Path(directory) / "bad.tar.gz"
        shutil.copyfile(str(archive), str(bad))
        with bad.open("ab") as stream:
            stream.write(b"corruption")
        try:
            namespace["publish"](
                root,
                bad,
                signature,
                root / "keyring.gpg",
                product,
                before["component"],
                before["version"],
            )
        except namespace["ReleaseError"]:
            pass
        else:
            raise RuntimeError("invalid signature accepted")
    if namespace["command"](["fapolicyd-cli", "--dump-db"]).stdout != trust_before:
        raise RuntimeError("negative probe changed trust")
    # Confirm service-user execution still opens the enrolled file-based package.
    result = subprocess.run(
        ["sudo", "-n", "-H", "-u", product, "bash", str(path / "deploy"), "validate"],
        cwd=user.pw_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError("protected file-based validation failed")
    print("PASS: signature refusal left trust unchanged; protected launch validates")
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
            raise RuntimeError("host facts unavailable")
        print(result.stdout, end="")
    print("PASS: protected release probes; no outside-target writes or policy changes")


if __name__ == "__main__":
    try:
        run()
    except Exception:
        raise SystemExit(
            "FAIL: protected release probe (private diagnostics withheld)"
        ) from None
