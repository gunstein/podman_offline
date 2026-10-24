#!/usr/bin/env python3
"""Generated Secret -> init process probe, using only disposable offline resources."""

import argparse
import base64
import copy
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
import warnings
from contextlib import contextmanager
from pathlib import Path

import yaml
from secret_templates_test import image


class ProbeFailure(RuntimeError):
    """Only fixed messages and numeric status, safe for the public evidence log."""


def command(arguments, allowed=(0,)):
    """Never disclose argv or captured output, including failed command output."""
    result = subprocess.run(
        arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
        timeout=180,
    )
    if result.returncode not in allowed:
        raise ProbeFailure("command exit=" + str(result.returncode))
    return result


@contextmanager
def phase(label, cleanup=False):
    """Name each boundary; cleanup must not replace an already reported failure."""
    pending_failure = sys.exc_info()[0] is not None
    print("START: init probe " + label, flush=True)
    try:
        yield
    except Exception as error:
        # Exception messages may contain secrets. Only our own safe type is shown.
        detail = str(error) if isinstance(error, ProbeFailure) else "operation failed"
        if isinstance(error, subprocess.TimeoutExpired):
            detail = "command timed out"
        elif isinstance(error, OSError):
            detail = "OS error errno=" + str(error.errno)
        message = label + ": " + detail
        print("FAIL: init probe " + message, flush=True)
        if not (cleanup and pending_failure):
            raise ProbeFailure(message) from None
    else:
        print("PASS: init probe " + label, flush=True)


# No assertion traceback or private value can reach logs. The expected file is
# supplied independently of the product recipe/renderer, as a test-only Secret.
CHECK = """import hashlib,os,sys,time
value = os.environ.get('APP_CONNECTIONSTRING')
expected = open('/run/secrets/expected/value').read()
if not value or value != expected or hashlib.sha256(value.encode()).hexdigest() != 'EXPECTED_DIGEST':
    print('PROBE-FAIL', flush=True)
    sys.exit(17)
print('PROBE-OK:' + os.environ['PROBE_RUN'], flush=True)
if os.environ['PROBE_ROLE'] == 'control':
    time.sleep(600)
"""

# Run the release's own modules in a fresh interpreter: no source import cache,
# synthetic HOME, host mutation or private values in argv. This is the rendering
# part of install, not a claim to exercise the complete production installer.
RENDER = """import sys
from pathlib import Path
from deployment import deploy, render
path, output, component = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
config = render.effective_config(render.load_config(path), path, component)
docs = deploy.validate_component(config, path, Path('components') / component / 'manifests', component)
text, volumes = render.materialize(config, path, docs, output.parent / 'files', component=component)
render.write_private(output, text)
"""


def private_yaml(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(yaml.safe_dump(value))
    path.chmod(0o600)


def fixture(source, name, probe_image):
    """A minimal renamed product: no demo app, gateway, database or registry."""
    repo = Path(__file__).resolve().parents[1]
    source.mkdir()
    for entry in ("deployment", "quadlet", "scripts"):
        shutil.copytree(
            repo / entry,
            source / entry,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    for entry in ("deploy.sh", "bundle.py", "README.md"):
        shutil.copy2(repo / entry, source / entry)
    private_yaml(source / "bundles.yaml", {"product": name, "components": {name: {}}})
    component = source / "components" / name
    component.mkdir(parents=True)
    (component / "VERSION").write_text("1.0.0\n")
    config = {
        "HOST": "default.invalid",
        "SECRET_FILES": {name + "-password": [{"path": "credentials/password"}]},
        "SECRET_TEMPLATES": {
            name + "-settings": {
                "connection-string": "Host=@@HOST@@;Password=@@secret:"
                + name
                + "-password/password@@"
            }
        },
    }
    private_yaml(component / "config.defaults.yaml", config)
    env = [
        {
            "name": "APP_CONNECTIONSTRING",
            "valueFrom": {
                "secretKeyRef": {"name": name + "-settings", "key": "connection-string"}
            },
        }
    ]
    container = {
        "name": "init",
        "image": probe_image,
        "imagePullPolicy": "Never",
        "command": ["python", "-c", CHECK],
        "env": env,
        "volumeMounts": [
            {"name": "expected", "mountPath": "/run/secrets/expected", "readOnly": True}
        ],
    }
    control = copy.deepcopy(container)
    control["name"] = "control"
    private_yaml(
        component / "manifests/pod.yaml",
        {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": name + "-job",
                "annotations": {"io.podman.annotations.init.container.type": "always"},
            },
            "spec": {
                "initContainers": [container],
                "containers": [control],
                "volumes": [
                    {"name": "expected", "secret": {"secretName": name + "-expected"}}
                ],
            },
        },
    )
    # A declaration is required for product validation. Runtime expectation is
    # independently replaced below, never read back from the rendered recipe.
    config["SECRET_TEMPLATES"][name + "-expected"] = {"value": "test-only"}
    private_yaml(component / "config.defaults.yaml", config)
    return config


def instrument(rendered, manifest, name, expected, nonce):
    """Add the independent private oracle and a public per-execution marker."""
    docs = list(yaml.safe_load_all(rendered.read_text()))
    oracle = next(d for d in docs if d["metadata"]["name"] == name + "-expected")
    oracle["data"]["value"] = base64.b64encode(expected.encode()).decode()
    for doc in docs:
        if doc["kind"] != "Pod":
            continue
        for group, role in (("initContainers", "init"), ("containers", "control")):
            for container in doc["spec"][group]:
                container["command"][-1] = CHECK.replace(
                    "EXPECTED_DIGEST", hashlib.sha256(expected.encode()).hexdigest()
                )
                container["env"] += [
                    {"name": "PROBE_RUN", "value": nonce},
                    {"name": "PROBE_ROLE", "value": role},
                ]
    manifest.write_text(yaml.safe_dump_all(docs))
    manifest.chmod(0o600)


def verify(name, nonce, timeout=60):
    """An exited always-init must succeed itself; a healthy main is insufficient."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        complete = []
        for role in ("init", "control"):
            target = name + "-job-" + role
            result = command(["podman", "inspect", target], allowed=(0, 1, 125))
            if result.returncode:
                complete.append(False)
                continue
            state = json.loads(result.stdout)[0]["State"]
            logs = command(["podman", "logs", target])
            if "PROBE-FAIL" in logs.stdout + logs.stderr:
                raise ProbeFailure("Secret probe " + role + ": process value mismatch")
            if state["Status"] == "exited" and state.get("ExitCode") != 0:
                raise ProbeFailure("Secret probe " + role + ": non-zero exit")
            marker = "PROBE-OK:" + nonce
            complete.append(
                marker in logs.stdout.splitlines()
                and (
                    state["Status"] == "exited" and state.get("ExitCode") == 0
                    if role == "init"
                    else state["Status"] == "running"
                )
            )
        if all(complete):
            return
        time.sleep(1)
    raise ProbeFailure(
        "Secret probe init/control: missing, stale or timed out assertion"
    )


def render_release(release, config_path, output, name):
    result = subprocess.run(
        [sys.executable, "-B", "-c", RENDER, str(config_path), str(output), name],
        cwd=str(release),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )
    if result.returncode:
        raise ProbeFailure("release renderer exit=" + str(result.returncode))


def cleanup(unit, manifest, name, unit_started, played):
    """Attempt every owned cleanup even if an earlier cleanup command fails."""
    failures = []
    if unit_started:
        try:
            command(["systemctl", "--user", "stop", name + ".service"])
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            failures.append(True)
    if played:
        # A successful Quadlet stop may already have removed the pod.
        try:
            exists = command(["podman", "pod", "exists", name + "-job"], allowed=(0, 1))
            if exists.returncode == 0:
                command(["podman", "kube", "down", str(manifest)])
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            failures.append(True)
    if unit.exists():
        try:
            unit.unlink()
            command(["systemctl", "--user", "daemon-reload"])
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            failures.append(True)
    # kube down can leave Secret-backed volumes behind. Never enumerate/remove
    # unrelated volumes or secrets. All three IDs belong to this UUID fixture.
    for suffix in ("-password", "-settings", "-expected"):
        try:
            exists = command(
                ["podman", "volume", "exists", name + suffix], allowed=(0, 1)
            )
            if exists.returncode == 0:
                command(["podman", "volume", "rm", name + suffix])
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            failures.append(True)
    if failures:
        raise ProbeFailure("Secret probe cleanup failed (owned resources only)")


def run(probe_image=None):
    if os.geteuid() == 0 or not os.environ.get("XDG_RUNTIME_DIR"):
        raise ProbeFailure("Run as the rootless lab user with XDG_RUNTIME_DIR")
    os.umask(0o077)
    version = command(
        ["podman", "version", "--format", "{{.Client.Version}}"]
    ).stdout.strip()
    systemd = command(["systemctl", "--version"]).stdout.splitlines()[0]
    if not re.fullmatch(r"[0-9]+(?:[.][0-9]+)+(?:[-+][A-Za-z0-9.]+)?", version):
        raise ProbeFailure("Secret probe could not identify Podman version")
    if not re.fullmatch(r"systemd [0-9]+.*", systemd):
        raise ProbeFailure("Secret probe could not identify systemd version")
    print("INFO: Podman " + version + "; " + systemd)
    name = "init-probe-" + uuid.uuid4().hex[:12]
    probe_image = probe_image or image("app1", "backend")
    command(["podman", "image", "exists", probe_image])
    # A disposable localhost alias prevents bundle's registry refresh policy from
    # requiring a network connection, even for an explicitly supplied image.
    alias = "localhost/" + name + ":probe"
    command(["podman", "tag", probe_image, alias])
    try:
        # Image archives and their extracted copies need disk space. The user
        # runtime directory is usually a small tmpfs reserved for runtime state.
        with tempfile.TemporaryDirectory(
            prefix=name + "-", dir=str(Path.home())
        ) as directory:
            root = Path(directory)
            source = root / "source"
            config = fixture(source, name, alias)
            password = secrets.token_hex(24)
            retained = (password + "\n").encode()
            dev_password = source / "build/dev" / name / "credentials/password"
            dev_password.parent.mkdir(parents=True)
            dev_password.write_bytes(retained)
            dev_password.chmod(0o600)
            manifest = root / "runtime.yaml"
            unit = Path.home() / ".config/containers/systemd" / (name + ".kube")
            unit.parent.mkdir(parents=True, exist_ok=True)
            played = unit_started = False
            try:
                for index in range(2):
                    host = "dev-" + str(index) + ".invalid"
                    private_yaml(
                        source / "components" / name / "config.dev.yaml", {"HOST": host}
                    )
                    command([str(source / "deploy.sh"), "prepare"])
                    nonce = uuid.uuid4().hex
                    instrument(
                        source / "build/install.yaml",
                        manifest,
                        name,
                        "Host=" + host + ";Password=" + password,
                        nonce,
                    )
                    played = True
                    command(["podman", "kube", "play", "--replace", str(manifest)])
                    verify(name, nonce)
                    if dev_password.read_bytes() != retained:
                        raise ProbeFailure("Secret probe changed retained dev password")
                    print(
                        "PASS: generated Secret init/control kube play "
                        + ("replacement" if index else "initial")
                    )
                with phase("stop direct kube pod"):
                    command(["podman", "kube", "down", str(manifest)])
                    played = False
                # Real bundle builder, then remove the entire source checkout.
                with phase("build and relocate bundle"):
                    command([sys.executable, "-B", str(source / "bundle.py")])
                    archive = next((source / "dist").glob("*-offline.tar.gz"))
                    release_parent = root / "relocated"
                    release_parent.mkdir()
                    with tarfile.open(str(archive)) as bundle:
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", DeprecationWarning)
                            bundle.extractall(str(release_parent))  # noqa: S202 - our own freshly built archive
                    release = next(release_parent.iterdir())
                    shutil.rmtree(source)
                config_path = root / "persistent/config.yaml"
                target_password = config_path.parent / "credentials/password"
                target_password.parent.mkdir(parents=True)
                target_password.write_bytes(retained)
                target_password.chmod(0o600)
                with phase("register Quadlet"):
                    unit.write_text("[Kube]\nYaml=" + str(manifest) + "\n")
                    unit.chmod(0o600)
                    command(["systemctl", "--user", "daemon-reload"])
                for index in range(2):
                    host = "prod-" + str(index) + ".invalid"
                    config["HOST"] = host
                    private_yaml(config_path, config)
                    output = root / "rendered.yaml"
                    with phase("render and instrument release"):
                        render_release(release, config_path, output, name)
                        nonce = uuid.uuid4().hex
                        instrument(
                            output,
                            manifest,
                            name,
                            "Host=" + host + ";Password=" + password,
                            nonce,
                        )
                    unit_started = played = True
                    with phase("start/restart Quadlet"):
                        command(
                            [
                                "systemctl",
                                "--user",
                                "restart" if index else "start",
                                name + ".service",
                            ]
                        )
                    with phase("verify Quadlet init/control processes"):
                        verify(name, nonce)
                    if target_password.read_bytes() != retained:
                        raise ProbeFailure(
                            "Secret probe changed retained production password"
                        )
                    print(
                        "PASS: generated Secret init/control relocated Quadlet "
                        + ("rerender/restart" if index else "initial")
                    )
            finally:
                with phase("remove owned resources", cleanup=True):
                    cleanup(unit, manifest, name, unit_started, played)
    finally:
        with phase("remove temporary image alias", cleanup=True):
            command(["podman", "untag", probe_image, alias])
    print("PASS: generated Secret init probe complete; owned resources removed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image", help="Already available image with python on PATH (standard library)"
    )
    try:
        run(parser.parse_args().image)
    except ProbeFailure as error:
        raise SystemExit("FAIL: generated Secret init probe: " + str(error)) from None
    except (
        RuntimeError,
        OSError,
        ValueError,
        KeyError,
        subprocess.TimeoutExpired,
        yaml.YAMLError,
    ):
        raise SystemExit(
            "FAIL: generated Secret init probe (diagnostics withheld)"
        ) from None
