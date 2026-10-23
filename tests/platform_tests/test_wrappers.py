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

ROOT = Path(__file__).resolve().parents[2]

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
uid = int(os.environ["FIXTURE_UID"])
os.getuid = os.geteuid = lambda: uid
pwd.getpwuid = lambda uid: pwd.struct_passwd(("fixture", "x", uid, uid, "", os.environ["FIXTURE_HOME"], "/bin/bash"))
user_runtime = "/run/user/" + str(uid)
is_dir = Path.is_dir
Path.is_dir = lambda path: True if str(path) == user_runtime else is_dir(path)
temporary_directory = tempfile.TemporaryDirectory
runtime = os.environ["XDG_RUNTIME_DIR"]
os.environ["XDG_RUNTIME_DIR"] = user_runtime
def staging(*args, **kwargs):
    if kwargs.get("dir") == user_runtime:
        kwargs["dir"] = runtime
    return temporary_directory(*args, **kwargs)
tempfile.TemporaryDirectory = staging
if "FIXTURE_ANCHOR" in os.environ:
    # The fixture's root-owned anchor is a temporary directory of this runner.
    from deployment import layout
    layout.ANCHOR = Path(os.environ["FIXTURE_ANCHOR"])
    layout.TRUSTED_TOP = layout.ANCHOR.parent
    layout.ROOT_UID = os.stat(os.environ["FIXTURE_ANCHOR"]).st_uid

def command(args, **kwargs):
    if args[0] not in ("podman", "systemctl"):
        raise AssertionError("Unexpected host command")
    with open(os.environ["FIXTURE_COMMANDS"], "a") as stream:
        stream.write(json.dumps(args) + "\\n")
    with open(os.environ["FIXTURE_COMMANDS"] + ".storage", "a") as stream:
        stream.write(json.dumps([args, os.environ.get("XDG_DATA_HOME"), os.environ.get("XDG_CONFIG_HOME")]) + "\\n")
    if args == ["systemctl", "--user", "show-environment"]:
        return subprocess.CompletedProcess(args, 0, stdout=os.environ["FIXTURE_MANAGER_ENV"], stderr="")
    if args[:2] == ["podman", "save"]:
        Path(args[4]).write_bytes(b"fixture image archive")
    if args[:3] == ["podman", "container", "inspect"]:
        healthy = '[{"State": {"Status": "running", "Health": {"Status": "healthy"}}}]'
        return subprocess.CompletedProcess(args, 0, stdout=healthy, stderr="")
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
            # A real production layout in miniature: the login home holds only
            # the bootstrap file; state, Quadlets and storage use the root.
            uid = os.geteuid() or 1000
            anchor = root / "var-lib"
            install = anchor / "myproduct"
            state = install / "state"
            for path in (anchor, install):
                path.mkdir(mode=0o755)
            for name in ("state", "config", "storage"):
                (install / name).mkdir(mode=0o700)
            bootstrap = home / ".myproduct/myproduct.env"
            bootstrap.parent.mkdir(mode=0o700)
            bootstrap.write_text(
                "# installation settings\nAPP_SETTING=$(touch "
                + str(root / "executed")
                + ")\nINSTALL_ROOT='"
                + str(install)
                + "'\n"
            )
            bootstrap.chmod(0o600)
            os.chmod(str(home), 0o755)
            if os.geteuid() == 0:
                for path in [home, bootstrap.parent, bootstrap] + [
                    install / name for name in ("state", "config", "storage")
                ]:
                    os.chown(str(path), uid, uid)
            for name in (
                "deploy",
                "bundle.py",
                "build-bundle.sh",
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
                                "upgrade": "newer-only",
                                "accepts": {"routes": "platform-routes"},
                            },
                            "identity": {
                                "requires": ["platform"],
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
                (folder / "VERSION").write_text("1.0.0\n")
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
                FIXTURE_UID=str(uid),
                FIXTURE_ANCHOR=str(anchor),
                FIXTURE_MANAGER_ENV=f"XDG_CONFIG_HOME={install}/config\nXDG_DATA_HOME={install}/storage\n",
                FIXTURE_COMMANDS=str(commands),
                XDG_RUNTIME_DIR=str(root / "runtime"),
            )
            env.pop("PYTHONDONTWRITEBYTECODE", None)
            env.pop("BUNDLE_SIGNING_KEY", None)  # Unsigned unless a test asks.
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
            version = (source / "components/app1/VERSION").read_text().strip()
            extracted = root / "extracted"
            extracted.mkdir()
            bundle_path = (
                source / "dist" / ("myproduct-app1-" + version + "-offline.tar.gz")
            )
            # Generated here from our fixture, with no external tar members.
            # Keep the Python 3.6 API; newer Python warns about its default.
            with tarfile.open(str(bundle_path)) as archive:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    archive.extractall(str(extracted))
            release = extracted / ("myproduct-app1-" + version)
            platform_version = (
                (source / "components/platform/VERSION").read_text().strip()
            )
            platform_tar = (
                source
                / "dist"
                / ("myproduct-platform-" + platform_version + "-offline.tar.gz")
            )
            with tarfile.open(str(platform_tar)) as archive:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    archive.extractall(str(extracted))
            platform_release = extracted / ("myproduct-platform-" + platform_version)
            run(platform_release, "deploy", "init-config", "platform")
            run(platform_release, "deploy", "install")
            identity_version = (
                (source / "components/identity/VERSION").read_text().strip()
            )
            identity_tar = (
                source
                / "dist"
                / ("myproduct-identity-" + identity_version + "-offline.tar.gz")
            )
            with tarfile.open(str(identity_tar)) as archive:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    archive.extractall(str(extracted))
            identity_release = extracted / ("myproduct-identity-" + identity_version)
            run(identity_release, "deploy", "init-config", "identity")
            run(identity_release, "deploy", "install")
            run(release, "deploy", "init-config", "app1")
            # Persistent settings override deliberately different release defaults.
            config = state / "app1/config.yaml"
            config_before = config.read_bytes()
            (release / "config/common.defaults.yaml").write_text(
                "PUBLIC_ORIGIN: https://changed.test:443\nHTTPS_PORT: 443\n"
            )
            run(release, "deploy", "install")
            self.assertEqual(config.read_bytes(), config_before)
            self.assertIn("fixture.test", (state / "platform/config.yaml").read_text())
            self.assertEqual((state / "installed/app1").read_text().strip(), version)
            run(release, "deploy", "uninstall")
            for folder in (source, extracted):
                self.assertFalse(list(folder.rglob("__pycache__")))
                self.assertFalse(list(folder.rglob("*.pyc")))
            self.assertFalse((state / "installed/app1").exists())
            self.assertTrue((state / "installed/platform").exists())
            self.assertEqual(config.read_bytes(), config_before)
            calls = [json.loads(line) for line in commands.read_text().splitlines()]
            self.assertIn(
                ["podman", "load", "-i", str(release / "images/images.tar")], calls
            )
            self.assertEqual(
                sorted(path.name for path in caller.iterdir()), ["config.yaml"]
            )
            self.assertEqual((caller / "config.yaml").read_bytes(), before)
            # Only the bootstrap file is in the login home; the unknown,
            # command-like setting was never executed.
            self.assertEqual(
                sorted(str(path.relative_to(home)) for path in home.rglob("*")),
                [".myproduct", ".myproduct/myproduct.env"],
            )
            self.assertFalse((root / "executed").exists())
            self.assertTrue(
                (
                    install / "config/containers/systemd/myproduct-platform.kube"
                ).is_file()
            )
            storage = [
                json.loads(line)
                for line in (root / "commands.jsonl.storage").read_text().splitlines()
            ]
            # Bundle building never inherits production storage; every
            # production Podman command uses the installation storage.
            self.assertIn(
                [
                    ["podman", "load", "-i", str(release / "images/images.tar")],
                    str(install / "storage"),
                    str(install / "config"),
                ],
                storage,
            )
            for args, data, config_home in storage:
                if args[0] != "podman":
                    continue
                if args[1] in ("save", "pull"):
                    self.assertEqual((data, config_home), (None, None), args)
                else:
                    self.assertEqual(
                        (data, config_home),
                        (str(install / "storage"), str(install / "config")),
                        args,
                    )
