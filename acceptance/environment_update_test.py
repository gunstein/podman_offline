#!/usr/bin/env python3
"""ENVIRONMENT changes reach the running containers on the next dev up.

The developer's flow, with the real command both times and nothing reset in
between: ./dev/dev.sh up; add a variable to the component's
config.defaults.yaml and override one regular-container and one
init-container variable in config/dev.yaml's overrides block (backlog 84);
./dev/dev.sh up again. Uses a disposable one-component product (unique name,
existing local image); only its own pod, volumes, network and image alias are
removed afterwards. Prints only the test variables' names and fixed
messages, never the environment or a credential.
"""

import hashlib
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from init_secret_test import ProbeFailure, command, private_yaml
from secret_templates_test import image

EXISTING = ("EXISTING_SETTING", "original")
ADDED = ("ADDED_SETTING", "environment-update-test")
# Common value, then the value of config/dev.yaml's override.
OVERRIDDEN = ("OVERRIDDEN_SETTING", "common", "dev-override")
INIT = ("INIT_SETTING", "common-init", "dev-init-override")
# The init container prints its variable; observe reads that line back.
INIT_PRINT = (
    "import os; print('INIT_SETTING=' + os.environ.get('INIT_SETTING', '<unset>'))"
)


@contextmanager
def phase(label):
    """START/PASS/FAIL per step; only this probe's fixed messages are shown."""
    print("START: environment update probe " + label, flush=True)
    try:
        yield
    except ProbeFailure as error:
        print("FAIL: environment update probe " + label + ": " + str(error), flush=True)
        raise
    except (OSError, subprocess.TimeoutExpired):
        print(
            "FAIL: environment update probe " + label + ": command failed", flush=True
        )
        raise ProbeFailure(label + " failed") from None
    print("PASS: environment update probe " + label, flush=True)


def write_product(source, name, alias):
    """Tool files of this checkout plus one component; nothing of the demo."""
    repo = Path(__file__).resolve().parents[1]
    source.mkdir()
    for entry in ("deployment", "quadlet", "scripts"):
        command(["cp", "-a", str(repo / entry), str(source / entry)])
    (source / "dev").mkdir()
    for entry in ("deploy.sh", "bundle.py", "README.md", "dev/dev.sh"):
        command(["cp", "-a", str(repo / entry), str(source / entry)])
    private_yaml(source / "bundles.yaml", {"product": name, "components": [name]})
    component = source / "components" / name
    (component / "manifests").mkdir(parents=True)
    (component / "VERSION").write_text("1.0.0\n")
    pod = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": name + "-web",
            # Kept after it exits, so its output can be read.
            "annotations": {"io.podman.annotations.init.container.type": "always"},
        },
        "spec": {
            "initContainers": [
                {
                    "name": "setup",
                    "image": alias,
                    "imagePullPolicy": "Never",
                    "command": ["python", "-c", INIT_PRINT],
                }
            ],
            "containers": [
                {
                    "name": "app",
                    "image": alias,
                    "imagePullPolicy": "Never",
                    "command": ["python", "-c", "import time; time.sleep(3600)"],
                }
            ],
        },
    }
    private_yaml(component / "manifests/pod.yaml", pod)
    write_defaults(source, name, {EXISTING[0]: EXISTING[1]})


def write_defaults(source, name, settings):
    """The component's config.defaults.yaml: a generated secret and ENVIRONMENT."""
    environment = dict(
        settings,
        TOKEN="@@secret:" + name + "-token/value@@",
        **{OVERRIDDEN[0]: OVERRIDDEN[1]},
    )
    private_yaml(
        source / "components" / name / "config.defaults.yaml",
        {
            "SECRET_FILES": {
                name + "-token": [{"path": "credentials/token", "generate": ["value"]}]
            },
            "ENVIRONMENT": {"app": environment, "setup": {INIT[0]: INIT[1]}},
        },
    )


def write_dev_overrides(source, name):
    """config/dev.yaml with only the overrides block: one variable per container."""
    private_yaml(
        source / "config/dev.yaml",
        {
            "overrides": {
                name: {
                    "ENVIRONMENT": {
                        "app": {OVERRIDDEN[0]: OVERRIDDEN[2]},
                        "setup": {INIT[0]: INIT[2]},
                    }
                }
            }
        },
    )


def observe(container, init, secret):
    """The running container's ID, the test variables of both containers, the secret's hash."""
    deadline = time.monotonic() + 60
    while True:
        state = command(
            ["podman", "inspect", "--format", "{{.Id}} {{.State.Status}}", container],
            allowed=(0, 125),
        ).stdout.split()
        if state[1:] == ["running"]:
            break
        if time.monotonic() >= deadline:
            raise ProbeFailure("container " + container + " is not running after 60s")
        time.sleep(2)
    values = {}
    for variable in (EXISTING[0], ADDED[0], OVERRIDDEN[0]):
        result = command(
            ["podman", "exec", container, "printenv", variable], allowed=(0, 1)
        )
        values[variable] = (
            result.stdout.rstrip("\n") if result.returncode == 0 else None
        )
    # The newest line the init container printed in this pod.
    printed = [
        line[len(INIT[0]) + 1 :]
        for line in command(["podman", "logs", init]).stdout.splitlines()
        if line.startswith(INIT[0] + "=")
    ]
    values[INIT[0]] = printed[-1] if printed else None
    return {
        "id": state[0],
        "values": values,
        "secret": hashlib.sha256(secret.read_bytes()).hexdigest(),
    }


def check(before, after):
    """The verdict on the two observations; raise ProbeFailure with a fixed text."""
    if before["values"] != {
        EXISTING[0]: EXISTING[1],
        ADDED[0]: None,
        OVERRIDDEN[0]: OVERRIDDEN[1],
        INIT[0]: INIT[1],
    }:
        raise ProbeFailure("first up: unexpected test variables before the change")
    if after["id"] == before["id"]:
        raise ProbeFailure("second up did not replace the container")
    if after["values"].get(ADDED[0]) != ADDED[1]:
        raise ProbeFailure(ADDED[0] + " is missing or wrong in the new container")
    if after["values"].get(EXISTING[0]) != EXISTING[1]:
        raise ProbeFailure(EXISTING[0] + " changed in the new container")
    if after["values"].get(OVERRIDDEN[0]) != OVERRIDDEN[2]:
        raise ProbeFailure(OVERRIDDEN[0] + " lacks the config/dev.yaml override")
    if after["values"].get(INIT[0]) != INIT[2]:
        raise ProbeFailure(INIT[0] + " lacks the override in the init container")
    if after["secret"] != before["secret"]:
        raise ProbeFailure("the generated secret changed between the two ups")


def cleanup(source, name, played):
    """Remove only this product's pod, volumes, network and image alias."""
    failures = 0
    steps = []
    if played:
        steps.append([str(source / "dev/dev.sh"), "down"])
    for volume in (
        name + "-token",
        name + "-app-env",
        name + "-app-env-secret",
        name + "-setup-env",
    ):
        steps.append(
            [
                "sh",
                "-c",
                'podman volume exists "$1" && podman volume rm "$1" || true',
                "-",
                volume,
            ]
        )
    steps.append(
        [
            "sh",
            "-c",
            'podman network exists "$1" && podman network rm "$1" || true',
            "-",
            name,
        ]
    )
    steps.append(["podman", "rmi", "localhost/" + name + ":probe"])
    for step in steps:
        try:
            command(step)
        except (ProbeFailure, OSError, subprocess.TimeoutExpired):
            failures += 1
    if failures:
        raise ProbeFailure(
            "environment update probe cleanup failed (owned resources only)"
        )


def run():
    name = "envup-" + uuid.uuid4().hex[:12]
    alias = "localhost/" + name + ":probe"
    command(["podman", "tag", image("app1", "backend"), alias])
    with tempfile.TemporaryDirectory(
        prefix=name + "-", dir=str(Path.home())
    ) as directory:
        source = Path(directory) / "source"
        container = name + "-web-app"
        init = name + "-web-setup"
        secret = source / "build/dev" / name / "credentials/token/value"
        played = False
        try:
            with phase("write the one-component product"):
                write_product(source, name, alias)
            with phase("first dev up"):
                played = True
                command([str(source / "dev/dev.sh"), "up"])
                before = observe(container, init, secret)
            with phase("add " + ADDED[0] + " to config.defaults.yaml"):
                write_defaults(
                    source, name, {EXISTING[0]: EXISTING[1], ADDED[0]: ADDED[1]}
                )
            with phase("override two variables in config/dev.yaml"):
                write_dev_overrides(source, name)
            with phase("second dev up"):
                command([str(source / "dev/dev.sh"), "up"])
                after = observe(container, init, secret)
            with phase("check the running container"):
                check(before, after)
            print(
                "PASS: dev/dev.sh up again delivered " + ADDED[0] + " and the "
                "config/dev.yaml overrides of "
                + OVERRIDDEN[0]
                + " and "
                + INIT[0]
                + " (init container) to a new container; "
                + EXISTING[0]
                + " and the generated secret kept"
            )
        finally:
            failed = sys.exc_info()[0] is not None
            try:
                with phase("cleanup"):
                    cleanup(source, name, played)
            except ProbeFailure:
                if not failed:
                    raise


if __name__ == "__main__":
    try:
        run()
    except ProbeFailure:
        raise SystemExit(
            "FAIL: environment update probe (see the step above)"
        ) from None
