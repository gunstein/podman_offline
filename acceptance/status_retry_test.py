"""Opt-in disposable PROD probe: same-version failure, status and real container retry.

Controller delivers this module on stdin. Protected release files and trust are
never changed. Only the demo's public config marker is edited, then restored.
"""
# ruff: noqa: UP021, UP022
# Guest-side code supports the product's Python 3.6 baseline.

import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import yaml

KEY = "DEMO_CONFIG_LAYER"
INJECTED = "STATUS_RETRY_DAEMON_RELOAD_INJECTED"
FAIL_INSTALL = r"""
import subprocess
import sys
sys.path.insert(0, sys.argv[1])
from deployment import cli
real_run = subprocess.run
injected = False

def command(args, **kwargs):
    global injected
    if list(map(str, args)) == ["systemctl", "--user", "daemon-reload"]:
        injected = True
        raise subprocess.CalledProcessError(73, args)
    return real_run(args, **kwargs)

subprocess.run = command
sys.argv = ["deploy.sh", "install"]
code = cli.main()
if injected and code == 1:
    print("STATUS_RETRY_DAEMON_RELOAD_INJECTED")
    raise SystemExit(73)
raise SystemExit(74)
"""


class ProbeError(Exception):
    """Fixed public diagnostics; never include config or captured output."""


def require(condition, message):
    if not condition:
        raise ProbeError(message)


def command(args, allowed=(0,), source=None):
    result = subprocess.run(
        args,
        input=source,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
        timeout=300,
    )
    require(result.returncode in allowed, "unexpected command exit")
    return result


def snapshot(*roots):
    """Hash private state in memory; never emit bytes, paths or hashes."""
    result = {}
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                result[str(path)] = ("link", os.readlink(str(path)))
            elif path.is_file():
                result[str(path)] = (
                    path.stat().st_mode,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            elif path.is_dir():
                result[str(path)] = (path.stat().st_mode, None)
            else:
                raise ProbeError("unexpected state file type")
    return result


def check_status(release, state, config_root, product, component, version, complete):
    before = snapshot(state, config_root)
    result = command(
        ["bash", str(release / "deploy.sh"), "status", "--json"], allowed=(0, 1)
    )
    require(snapshot(state, config_root) == before, "status changed persistent files")
    require(result.returncode == (0 if complete else 1), "wrong status exit")
    report = json.loads(result.stdout)
    require(report["product"] == product, "wrong status product")
    rows = [row for row in report["components"] if row["name"] == component]
    require(len(rows) == 1, "missing or duplicate status component")
    row = rows[0]
    require(
        row["version"] == version == row["recorded_version"],
        "completed/recorded version changed",
    )
    require(
        row["state"] == "active" and row["complete"] is complete,
        "wrong active/completion state",
    )
    expected = (
        None
        if complete
        else {"operation": "install", "component": component, "owners": []}
    )
    require(report["pending"] == expected, "wrong pending install/owners")


def rendered_value(output):
    values = [
        doc["data"][KEY]
        for doc in yaml.safe_load_all(output.read_text())
        if doc and doc.get("kind") == "ConfigMap" and KEY in doc.get("data", {})
    ]
    require(len(values) == 1, "missing or ambiguous public ConfigMap marker")
    return values[0]


def running_value(container):
    return command(["podman", "exec", container, "printenv", KEY]).stdout.rstrip("\n")


def container_id(container):
    return command(
        ["podman", "inspect", "--format", "{{.Id}}", container]
    ).stdout.strip()


def run(release, component):
    require(os.geteuid() != 0, "run as the product runtime account")
    descriptor = yaml.safe_load((release / "bundle.yaml").read_text())
    require(
        descriptor["name"] == component and descriptor["upgrade"] == "always",
        "requires selected upgrade-always bundle",
    )
    product, version = descriptor["product"], descriptor["version"]
    state = Path(os.environ["PRODUCT_STATE"])
    config_root = Path(os.environ["XDG_CONFIG_HOME"])
    config_path = state / component / "config.yaml"
    original = config_path.read_bytes()
    config = yaml.safe_load(original)
    require(isinstance(config.get(KEY), str), "requires public demo config marker")
    old = config[KEY]
    output = config_root / "containers/systemd" / (product + "-" + component + ".yaml")
    container = component + "-todo-backend"
    check_status(release, state, config_root, product, component, version, True)
    require(
        rendered_value(output) == old == running_value(container),
        "baseline marker not consumed",
    )
    old_id = container_id(container)
    require(bool(old_id), "missing baseline container")
    marker = state / "installed" / component
    before_marker = marker.read_bytes()
    release_before = snapshot(release / "deployment", release / "quadlet")
    value = "status-retry-" + uuid.uuid4().hex
    config[KEY] = value
    try:
        config_path.write_text(yaml.safe_dump(config))
        result = command(
            [sys.executable, "-I", "-B", "-", str(release)],
            allowed=(73,),
            source=FAIL_INSTALL,
        )
        require(
            INJECTED in result.stdout.splitlines(), "failure injection was not reached"
        )
        require(
            rendered_value(output) == value,
            "new public value not rendered before failure",
        )
        require(
            container_id(container) == old_id and running_value(container) == old,
            "old container restarted or changed before retry",
        )
        require(
            marker.read_bytes() == before_marker, "failure changed completed version"
        )
        check_status(release, state, config_root, product, component, version, False)
        print(
            "PASS: same-version failure is pending/incomplete with old container active"
        )
        # A new, ordinary CLI process, with no injection or patched lifecycle functions.
        command(["bash", str(release / "deploy.sh"), "install"])
        require(
            rendered_value(output) == value == running_value(container),
            "retry value not consumed by container",
        )
        require(container_id(container) != old_id, "retry did not replace container")
        check_status(release, state, config_root, product, component, version, True)
        print("PASS: same-version retry completed and new public value is live")
    finally:
        # Restore through the same lifecycle; never remove pending state by hand.
        config_path.write_bytes(original)
        command(["bash", str(release / "deploy.sh"), "install"])
        require(
            rendered_value(output) == old == running_value(container),
            "restored value not consumed",
        )
        check_status(release, state, config_root, product, component, version, True)
        require(
            snapshot(release / "deployment", release / "quadlet") == release_before,
            "protected release changed",
        )
    print("PASS: original config restored through install; protected code unchanged")


def main():
    try:
        run(Path(sys.argv[1]), sys.argv[2])
    except Exception as error:  # noqa: BLE001 - never expose private probe/command data
        message = str(error) if isinstance(error, ProbeError) else type(error).__name__
        print("FAIL: status retry probe: " + message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
