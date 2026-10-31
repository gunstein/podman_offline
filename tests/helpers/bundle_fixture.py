"""Build real bundle archives with only the Podman subprocess stubbed."""

import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import bundle
import yaml

from helpers.catalog_fixture import DEMO_COMPONENTS


class BundleFixture(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        # Builds sign only when the operator asks; the caller's key is not ours.
        self.stack.enter_context(mock.patch.dict(os.environ))
        os.environ.pop(bundle.SIGNING_KEY, None)
        self.stack.enter_context(
            mock.patch.multiple(
                bundle,
                ROOT=self.root,
                STAGE=self.root / "build/bundle",
                DIST=self.root / "dist",
            )
        )
        self.output = self.stack.enter_context(
            contextlib.redirect_stdout(io.StringIO())
        )
        self.errors = self.stack.enter_context(
            contextlib.redirect_stderr(io.StringIO())
        )
        self.process = self.stack.enter_context(
            mock.patch.object(subprocess, "run", side_effect=self.save)
        )
        for name, text in {
            "VERSION": "1.2.3\n",
            "deploy.sh": '#!/bin/sh\nexec python3 -B -m deployment "$@"\n',
            "deployment/__init__.py": "",
            "deployment/__main__.py": "print('test fixture')\n",
            "README.md": "Test fixture only\n",
            "config.defaults.yaml": "HTTPS_PORT: 8443\n",
            "dev/generate-certificates.sh": "#!/bin/sh\nexit 0\n",
            "scripts/prepare-host.sh": "#!/bin/sh\nexit 0\n",
            "dev/dev.sh": "#!/bin/sh\nexit 0\n",
            "dev/build-images.sh": "#!/bin/sh\nexit 0\n",
            "dev/smoke-test.py": "print('dev only')\n",
            "quadlet/template.kube": "[Kube]\nYaml=@@UNIT_NAME@@.yaml\n",
            "quadlet/template.network": "[Network]\nNetworkName=@@PRODUCT_NAME@@\n",
            "manifests/app.yaml": "kind: Pod\nspec:\n  initContainers:\n  - image: localhost/init:1\n  containers:\n  - name: app\n    image: localhost/app:1\n    imagePullPolicy: Never\n",
        }.items():
            self.write(name, text)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def save(self, args, check, **kwargs):
        """Stub registry pulls and write deterministic bytes for the multi-image save."""
        self.assertTrue(check)
        if args[:2] == ["podman", "pull"]:
            self.assertEqual(args[2], "--policy=always")
            self.assertEqual(
                kwargs, {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
            )
            return
        self.assertEqual(args[:4], ["podman", "save", "-m", "-o"])
        Path(args[4]).write_bytes(("stub images " + " ".join(args[5:])).encode("utf-8"))

    def archive_bytes(self, archive, name):
        stream = archive.extractfile("myproduct-1.2.3/" + name)
        self.assertIsNotNone(stream)
        assert stream is not None
        with stream:
            return stream.read()

    def write_component_catalog(self):
        """Write the demo catalog without registrations: no route/client files."""
        self.write(
            "bundles.yaml",
            yaml.safe_dump(
                {
                    "product": "myproduct",
                    "gateway": "platform",
                    "identity": "identity",
                    "components": list(DEMO_COMPONENTS),
                }
            ),
        )
        self.write("components/platform/VERSION", "1.0.0\n")
        self.write("components/identity/VERSION", "1.1.0\n")
        self.write("config/common.defaults.yaml", "HTTPS_PORT: 8443\n")
        for component in ("app1", "app2", "help"):
            self.write("components/" + component + "/VERSION", "1.2.3\n")
        for component in ("platform", "identity", "app1", "app2", "help"):
            self.write(
                "components/" + component + "/manifests/pod.yaml",
                yaml.safe_dump(
                    {
                        "kind": "Pod",
                        "spec": {
                            "containers": [{"image": "localhost/" + component + ":1"}]
                        },
                    }
                ),
            )
            self.write(
                "components/" + component + "/config.defaults.yaml",
                "HTTPS_PORT: 8443\n",
            )
            self.write(
                "components/" + component + "/config.yaml", "PRIVATE: do-not-bundle\n"
            )
