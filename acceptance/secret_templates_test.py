#!/usr/bin/env python3
"""Disposable Secret env/file/restart probe; values never reach argv or evidence.

Run as the rootless lab user after dev/build-images.sh. This writes one private
UUID-scoped kube YAML and Quadlet and removes only its own resources afterwards.
On the hardened target, the installed-product checks also test policy and logs.
"""

import argparse
import base64
import json
import os
import secrets
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import yaml

CHECK = (
    "import os,time; "
    "assert os.environ['PROBE_VALUE'] == open('/run/secrets/probe/value').read(); "
    "print('Secret env and file verified', flush=True); time.sleep(600)"
)


def command(arguments, allowed=(0,)):
    """Capture all diagnostics; even Podman errors can contain private content."""
    result = subprocess.run(
        arguments, capture_output=True, text=True, check=False, timeout=180
    )
    if result.returncode not in allowed:
        raise RuntimeError("Secret probe command failed (diagnostics withheld)")
    return result


def documents(name, value, probe_image):
    """Hand-written Kubernetes input, independent of the product renderer."""
    return [
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": name},
            "data": {"value": base64.b64encode(value.encode()).decode()},
        },
        {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": name},
            "spec": {
                "containers": [
                    {
                        "name": "check",
                        "image": probe_image,
                        "imagePullPolicy": "Never",
                        "command": ["python", "-c", CHECK],
                        "env": [
                            {
                                "name": "PROBE_VALUE",
                                "valueFrom": {
                                    "secretKeyRef": {"name": name, "key": "value"}
                                },
                            }
                        ],
                        "volumeMounts": [
                            {
                                "name": "secret",
                                "mountPath": "/run/secrets/probe",
                                "readOnly": True,
                            }
                        ],
                    }
                ],
                "volumes": [
                    {
                        "name": "secret",
                        "secret": {
                            "secretName": name,
                            "items": [{"key": "value", "path": "value"}],
                        },
                    }
                ],
            },
        },
    ]


def verify(name, expected):
    """Require the new env value and actual file equality; print only the finding."""
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        inspected = command(["podman", "inspect", name + "-check"], allowed=(0, 1, 125))
        if inspected.returncode == 0:
            rows = json.loads(inspected.stdout)
            container = rows[0]
            logs = command(["podman", "logs", name + "-check"])
            if (
                container["State"]["Status"] == "running"
                and "Secret env and file verified" in logs.stdout
            ):
                if "PROBE_VALUE=" + expected not in container["Config"]["Env"]:
                    raise RuntimeError(
                        "Secret update did not reach container environment"
                    )
                if expected in logs.stdout + logs.stderr:
                    raise RuntimeError(
                        "Secret probe leaked its value in container logs"
                    )
                return
        time.sleep(1)
    raise RuntimeError(
        "Secret probe did not verify env and mounted file before deadline"
    )


def image(component, container):
    """Only the DEV default needs the source checkout; PROD can pass --image."""
    from database_test import image as source_image

    return source_image(component, container)


def run(probe_image=None):
    if os.geteuid() == 0 or not os.environ.get("XDG_RUNTIME_DIR"):
        raise RuntimeError(
            "Run Secret probe as the rootless lab user with XDG_RUNTIME_DIR"
        )
    os.umask(0o077)
    name = "secret-probe-" + uuid.uuid4().hex[:12]
    unit = Path.home() / ".config/containers/systemd" / (name + ".kube")
    unit.parent.mkdir(parents=True, exist_ok=True)
    probe_image = probe_image or image("app1", "backend")
    command(["podman", "image", "exists", probe_image])
    version = command(
        ["podman", "version", "--format", "{{.Client.Version}}"]
    ).stdout.strip()
    print("INFO: Podman " + version + "; rootless Secret env/file/restart probe")
    with tempfile.TemporaryDirectory(
        prefix=name + "-", dir=os.environ["XDG_RUNTIME_DIR"]
    ) as directory:
        manifest = Path(directory) / "probe.yaml"

        def write(value):
            manifest.write_text(yaml.safe_dump_all(documents(name, value, probe_image)))
            manifest.chmod(0o600)

        values = []
        try:
            for repeated in (False, True):
                value = secrets.token_hex(24)
                values.append(value)
                write(value)
                command(["podman", "kube", "play", "--replace", str(manifest)])
                verify(name, value)
                print(
                    "PASS: kube play secretKeyRef, mounted items and "
                    + ("replacement" if repeated else "initial value")
                )
            command(["podman", "kube", "down", str(manifest)])
            unit.write_text("[Kube]\nYaml=" + str(manifest) + "\n")
            unit.chmod(0o600)
            command(["systemctl", "--user", "daemon-reload"])
            for repeated in (False, True):
                value = secrets.token_hex(24)
                values.append(value)
                write(value)
                command(
                    [
                        "systemctl",
                        "--user",
                        "restart" if repeated else "start",
                        name + ".service",
                    ]
                )
                verify(name, value)
                print(
                    "PASS: Quadlet secretKeyRef, mounted items and "
                    + ("restart update" if repeated else "initial value")
                )
            journal = command(
                ["journalctl", "--user", "-u", name + ".service", "--no-pager"]
            )
            if any(value in journal.stdout + journal.stderr for value in values):
                raise RuntimeError("Secret probe leaked its value to user journal")
            print(
                "PASS: podman inspect exposes env value as expected; private values withheld"
            )
        finally:
            try:
                if unit.exists():
                    command(["systemctl", "--user", "stop", name + ".service"])
                    unit.unlink()
                    command(["systemctl", "--user", "daemon-reload"])
            finally:
                if manifest.exists():
                    command(["podman", "kube", "down", str(manifest)])
                exists = command(["podman", "volume", "exists", name], allowed=(0, 1))
                if exists.returncode == 0:
                    command(["podman", "volume", "rm", name])
    print("PASS: Secret probe complete; disposable resources removed")


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument(
            "--image",
            help="Already available image with Python; avoids source imports on PROD",
        )
        run(parser.parse_args().image)
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        raise SystemExit(
            "FAIL: Secret env/file/restart probe (diagnostics withheld)"
        ) from None
