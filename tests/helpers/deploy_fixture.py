"""Isolated renderer/installer tests; no Podman, systemd, root or network."""

import contextlib
import io
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import bundle
import yaml
from deployment import common, health, layout, output
from deployment import render as rendering


def document(kind, name, **values):
    result = {"apiVersion": "v1", "kind": kind, "metadata": {"name": name}}
    result.update(values)
    return result


class DeployFixture(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        # Builds sign only when the operator asks; the caller's key is not ours.
        self.stack.enter_context(mock.patch.dict(os.environ))
        os.environ.pop(bundle.SIGNING_KEY, None)
        paths = {
            "HOME": self.root / "home",
            # Production state shares the fixture home; layout.select is
            # replaced below and tested separately (test_layout.py).
            "STATE": self.root / "home",
            "ROOT": self.root,
            "CONFIG": self.root / "config.yaml",
            "MANIFESTS": self.root / "manifests",
            "BUILD": self.root / "build",
            "QUADLET_TEMPLATE": self.root / "quadlet/template.kube",
            "QUADLET_DIR": self.root / "home/.config/containers/systemd",
            "QUADLET_TARGET": self.root
            / "home/.config/containers/systemd/myproduct.kube",
            "QUADLET_YAML": self.root
            / "home/.config/containers/systemd/myproduct.yaml",
            "FILES_DIR": self.root / "home/files",
        }
        for name, path in paths.items():
            self.stack.enter_context(mock.patch.object(common, name, path))
        self.stack.enter_context(
            mock.patch.object(layout, "select", return_value=self.root / "install")
        )
        self.stack.enter_context(mock.patch.object(layout, "check_user_manager"))
        self.process = self.stack.enter_context(mock.patch.object(subprocess, "run"))
        # Containers report healthy unless a test says otherwise (backlog 34).
        self.container_state = self.stack.enter_context(
            mock.patch.object(
                health, "container_state", return_value=("running", "healthy")
            )
        )
        self.euid = self.stack.enter_context(
            mock.patch.object(os, "geteuid", return_value=1000)
        )
        runtime = Path("/run/user/1000")
        original_is_dir = Path.is_dir
        self.stack.enter_context(
            mock.patch.object(
                Path,
                "is_dir",
                lambda path: True if path == runtime else original_is_dir(path),
            )
        )
        self.stack.enter_context(
            mock.patch.dict(
                os.environ,
                {"XDG_RUNTIME_DIR": str(runtime), "HOME": str(self.root / "home")},
            )
        )
        # The environment guard is tested separately. Keep staging inside the
        # fixture, even on machines without the synthetic runtime directory.
        temporary_directory = tempfile.TemporaryDirectory

        def staging(*args, **kwargs):
            if kwargs.get("dir") == str(runtime):
                kwargs["dir"] = str(self.root)
            return temporary_directory(*args, **kwargs)

        self.stack.enter_context(
            mock.patch.object(tempfile, "TemporaryDirectory", side_effect=staging)
        )
        # Logging configuration is global: no host journal, and reset after.
        self.stack.enter_context(
            mock.patch.object(output, "SYSLOG", str(self.root / "no-journal"))
        )
        self.addCleanup(output.configure)
        self.stdout = self.stack.enter_context(
            contextlib.redirect_stdout(io.StringIO())
        )
        self.stderr = self.stack.enter_context(
            contextlib.redirect_stderr(io.StringIO())
        )
        common.MANIFESTS.mkdir()
        self.write("quadlet/template.kube", "[Kube]\nYaml=@@UNIT_NAME@@.yaml\n")
        self.write(
            "quadlet/template.network", "[Network]\nNetworkName=@@PRODUCT_NAME@@\n"
        )
        self.config = {"HTTPS_PORT": 8443, "HOSTNAME": "example.test"}
        self.write_config()

    def write(self, name, contents: object = b"test\n", mode=0o644):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contents, str):
            contents = contents.encode("utf-8")
        assert isinstance(contents, bytes)
        path.write_bytes(contents)
        path.chmod(mode)
        return path

    def write_config(self):
        self.write("config.yaml", yaml.safe_dump(self.config))
        if getattr(self, "production_config", False):
            self.write("home/config.yaml", yaml.safe_dump(self.config), 0o600)

    def manifest(self, docs, name="10-pod.yaml"):
        return self.write("manifests/" + name, yaml.safe_dump_all(docs))

    def file_config(self, group, spec):
        """Build source declarations from the tests' shorthand path specifications."""
        self.config[group] = (
            {
                name: [
                    {"path": value} if isinstance(value, str) else value
                    for value in sources
                ]
                if isinstance(sources, list)
                else sources
                for name, sources in spec.items()
            }
            if isinstance(spec, dict)
            else spec
        )
        self.write_config()
        return rendering.load_file_group(self.config, group)

    def volume_fixture(self):
        self.write("files/message.txt", "hello\n", 0o600)
        self.file_config("VOLUME_FILES", {"uploads": ["files/message.txt"]})
        self.manifest(
            [
                document(
                    "Pod",
                    "app",
                    spec={
                        "volumes": [
                            {
                                "name": "uploads",
                                "persistentVolumeClaim": {"claimName": "uploads"},
                            }
                        ]
                    },
                )
            ]
        )

    def install_fixture(self):
        self.volume_fixture()
        self.production_config = True
        self.stack.enter_context(
            mock.patch.dict(os.environ, {"HOME": str(self.root / "home")})
        )
        self.config["VOLUME_FILES"] = {"uploads": [{"path": "../files/message.txt"}]}
        self.write("quadlet/template.kube", "[Kube]\nYaml=@@UNIT_NAME@@.yaml\n")
        self.write(
            "quadlet/template.network", "[Network]\nNetworkName=@@PRODUCT_NAME@@\n"
        )
        self.write("images/images.tar")
        self.config["APP_IMAGE"] = "localhost/app:1"
        self.write_config()
        self.manifest(
            [
                {
                    "kind": "Pod",
                    "spec": {
                        "containers": [
                            {"image": "@@APP_IMAGE@@", "imagePullPolicy": "Never"},
                            {"image": "localhost/app:1", "imagePullPolicy": "Never"},
                        ],
                        "initContainers": [
                            {"image": "localhost/init:1", "imagePullPolicy": "Never"}
                        ],
                    },
                }
            ],
            "20-images.yaml",
        )

    def mode(self, path):
        return stat.S_IMODE(path.stat().st_mode)
