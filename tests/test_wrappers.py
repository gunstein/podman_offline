# ruff: noqa: UP021, UP022 - host/test code retains Python 3.6 APIs
"""Run actual entry points from an unrelated directory, using isolated host stubs."""

import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import warnings
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Loaded only by the child Python processes. Account/runtime policy has separate
# unit coverage; these tests exercise wrapper cwd, resources and config selection.
HOST_STUB = """
import json
import os
import pwd
import subprocess
import sys
from pathlib import Path
import tempfile
os.getuid = os.geteuid = lambda: 1000
pwd.getpwuid = lambda uid: pwd.struct_passwd(("fixture", "x", 1000, 1000, "", os.environ["FIXTURE_HOME"], "/bin/bash"))
is_dir = Path.is_dir
Path.is_dir = lambda path: True if str(path) == "/run/user/1000" else is_dir(path)
temporary_directory = tempfile.TemporaryDirectory
runtime = os.environ["XDG_RUNTIME_DIR"]
os.environ["XDG_RUNTIME_DIR"] = "/run/user/1000"
def staging(*args, **kwargs):
    if kwargs.get("dir") == "/run/user/1000":
        kwargs["dir"] = runtime
    return temporary_directory(*args, **kwargs)
tempfile.TemporaryDirectory = staging

def command(args, **kwargs):
    if args[0] not in ("podman", "systemctl"):
        raise AssertionError("Unexpected host command")
    with open(os.environ["FIXTURE_COMMANDS"], "a") as stream:
        stream.write(json.dumps(args) + "\\n")
    if args[:2] == ["podman", "save"]:
        Path(args[4]).write_bytes(b"fixture image archive")
    return subprocess.CompletedProcess(args, 1 if args[:3] == ["podman", "volume", "exists"] else 0, stdout=b"", stderr=b"")
subprocess.run = command
"""


class WrapperTests(unittest.TestCase):
    """Build/extract a real bundle and run each root command via its absolute path."""

    def test_source_and_release_commands_ignore_callers_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, caller, home, shim = [
                root / name for name in ("source", "caller", "home", "shim")
            ]
            for path in (source, caller, home, shim, root / "runtime"):
                path.mkdir()
            for name in (
                "deploy",
                "bundle.py",
                "build-bundle.sh",
                "VERSION",
                "PLATFORM_VERSION",
                "IDENTITY_VERSION",
                "README.md",
            ):
                shutil.copy2(ROOT / name, source / name)
            for name in ("deployment", "quadlet", "scripts"):
                shutil.copytree(
                    ROOT / name,
                    source / name,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
                )
            (source / "config").mkdir()
            (source / "config/common.defaults.yaml").write_text(
                "PUBLIC_ORIGIN: https://fixture.test:8443\nHTTPS_PORT: 8443\n"
            )
            (source / "bundles.yaml").write_text(
                yaml.safe_dump(
                    {
                        "product": "myproduct",
                        "components": {
                            "platform": {
                                "version_file": "PLATFORM_VERSION",
                                "upgrade": "newer-only",
                                "accepts": {"routes": "platform-routes"},
                            },
                            "identity": {
                                "requires": ["platform"],
                                "version_file": "IDENTITY_VERSION",
                                "upgrade": "newer-only",
                                "public_from": "platform",
                                "accepts": {"clients": "identity-clients"},
                            },
                            "app1": {
                                "requires": ["platform", "identity"],
                                "public_from": "platform",
                            },
                        },
                    }
                )
            )
            for component in ("platform", "identity", "app1", "app2", "help"):
                folder = source / "components" / component
                (folder / "manifests").mkdir(parents=True)
                (folder / "config.defaults.yaml").write_text("{}\n")
                (folder / "manifests/10-pod.yaml").write_text(
                    yaml.safe_dump(
                        {
                            "kind": "Pod",
                            "metadata": {"name": component + "-worker"},
                            "spec": {
                                "containers": [
                                    {
                                        "name": "worker",
                                        "image": "localhost/fixture:1",
                                        "imagePullPolicy": "Never",
                                    }
                                ],
                                "volumes": [
                                    {
                                        "name": name,
                                        "persistentVolumeClaim": {
                                            "claimName": component + "-" + name
                                        },
                                    }
                                    for name in (
                                        ("routes",)
                                        if component == "platform"
                                        else ("clients",)
                                    )
                                ]
                                if component in ("platform", "identity")
                                else [],
                            },
                        }
                    )
                )
            (shim / "sitecustomize.py").write_text(HOST_STUB)
            commands = root / "commands.jsonl"
            env = dict(
                os.environ,
                HOME=str(home),
                FIXTURE_HOME=str(home),
                FIXTURE_COMMANDS=str(commands),
                XDG_RUNTIME_DIR=str(root / "runtime"),
            )
            env.pop("PYTHONDONTWRITEBYTECODE", None)
            # A tempting, invalid caller config must never be read or overwritten.
            (caller / "config.yaml").write_text("invalid: [\n")
            before = (caller / "config.yaml").read_bytes()

            def run(folder, wrapper, *args):
                env["PYTHONPATH"] = os.pathsep.join((str(shim), str(folder)))
                result = subprocess.run(
                    [str(folder / wrapper)] + list(args),
                    check=False,
                    cwd=str(caller),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            run(source, "deploy", "prepare")
            self.assertTrue((source / "build/install.yaml").is_file())
            # This fixture has no database pods, so prepare needs no host commands.
            self.assertFalse(commands.exists())
            run(source, "build-bundle.sh")
            version = (source / "VERSION").read_text().strip()
            extracted = root / "extracted"
            extracted.mkdir()
            bundle_path = (
                source / "dist" / ("myproduct-app1-" + version + "-offline.tar.gz")
            )
            # Generated here from our fixture, with no external tar members.
            # Keep the Python 3.6 API; newer Python warns about its default.
            with tarfile.open(str(bundle_path)) as archive, warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                archive.extractall(str(extracted))
            release = extracted / ("myproduct-app1-" + version)
            platform_version = (source / "PLATFORM_VERSION").read_text().strip()
            platform_tar = (
                source
                / "dist"
                / ("myproduct-platform-" + platform_version + "-offline.tar.gz")
            )
            with tarfile.open(str(platform_tar)) as archive, warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                archive.extractall(str(extracted))
            platform_release = extracted / ("myproduct-platform-" + platform_version)
            run(platform_release, "deploy", "init-config", "platform")
            run(platform_release, "deploy", "install")
            identity_version = (source / "IDENTITY_VERSION").read_text().strip()
            identity_tar = (
                source
                / "dist"
                / ("myproduct-identity-" + identity_version + "-offline.tar.gz")
            )
            with tarfile.open(str(identity_tar)) as archive, warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                archive.extractall(str(extracted))
            identity_release = extracted / ("myproduct-identity-" + identity_version)
            run(identity_release, "deploy", "init-config", "identity")
            run(identity_release, "deploy", "install")
            run(release, "deploy", "init-config", "app1")
            # Persistent settings override deliberately different release defaults.
            config = home / "app1/config.yaml"
            config_before = config.read_bytes()
            (release / "config/common.defaults.yaml").write_text(
                "PUBLIC_ORIGIN: https://changed.test:443\nHTTPS_PORT: 443\n"
            )
            run(release, "deploy", "install")
            self.assertEqual(config.read_bytes(), config_before)
            self.assertIn("fixture.test", (home / "platform/config.yaml").read_text())
            self.assertEqual((home / "installed/app1").read_text().strip(), version)
            run(release, "deploy", "uninstall")
            for folder in (source, extracted):
                self.assertFalse(list(folder.rglob("__pycache__")))
                self.assertFalse(list(folder.rglob("*.pyc")))
            self.assertFalse((home / "installed/app1").exists())
            self.assertTrue((home / "installed/platform").exists())
            self.assertEqual(config.read_bytes(), config_before)
            calls = [json.loads(line) for line in commands.read_text().splitlines()]
            self.assertIn(
                ["podman", "load", "-i", str(release / "images/images.tar")], calls
            )
            self.assertEqual(
                sorted(path.name for path in caller.iterdir()), ["config.yaml"]
            )
            self.assertEqual((caller / "config.yaml").read_bytes(), before)
