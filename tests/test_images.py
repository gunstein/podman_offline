"""Test manifest-driven dev build and pull helpers with a recording Podman stub."""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


class ImageHelperTests(unittest.TestCase):
    """Exercise the actual shell helpers without Podman, networking or registry credentials."""

    def setUp(self):
        """Copy the helpers into an isolated repo and install a recording Podman executable."""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "dev").mkdir()
        (self.root / "manifests").mkdir()
        for name in (
            "bundle.py",
            "dev/build-images.sh",
            "dev/pull-images.sh",
        ):
            shutil.copy2(ROOT / name, self.root / name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        interpreter = self.bin / "python3"
        interpreter.write_text(
            "#!/bin/sh\nexec " + shlex.quote(sys.executable) + ' "$@"\n'
        )
        interpreter.chmod(0o755)
        stub = self.bin / "podman"
        stub.write_text(
            "#!" + sys.executable + "\n"
            "import json, os, sys\n"
            "with open(os.environ['IMAGE_COMMAND_LOG'], 'a') as stream:\n"
            "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "if os.environ.get('FAIL_PULL') and sys.argv[1] == 'pull':\n"
            "    print('private-auth-token', file=sys.stderr)\n"
            "    sys.exit(125)\n"
        )
        stub.chmod(0o755)
        self.log = self.root / "commands.jsonl"
        shutil.copytree(ROOT / "deployment", self.root / "deployment")
        self.env = dict(
            os.environ,
            PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
            IMAGE_COMMAND_LOG=str(self.log),
        )

    def manifest(self, images):
        """Write one Pod using the requested full image names."""
        (self.root / "manifests/app.yaml").write_text(
            yaml.safe_dump(
                {
                    "kind": "Pod",
                    "spec": {
                        "containers": [
                            {
                                "name": "app" + str(index),
                                "image": image,
                                "imagePullPolicy": "Never",
                            }
                            for index, image in enumerate(images)
                        ]
                    },
                }
            )
        )

    def helper(self, name):
        """Run a copied helper and return its result and recorded Podman arguments."""
        result = subprocess.run(  # noqa: UP022 - Python 3.6 lacks capture_output
            ["bash", str(self.root / "dev" / name)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,  # noqa: UP021 - Python 3.6 lacks text
            check=False,
            env=self.env,
        )
        calls = (
            [json.loads(line) for line in self.log.read_text().splitlines()]
            if self.log.exists()
            else []
        )
        return result, calls

    def test_build_uses_manifest_tag_and_pull_skips_local_images(self):
        """Build a local demo image with the manifest tag and avoid registry pulls."""
        self.manifest(["localhost/myproduct-help:1.2.3"])
        app = self.root / "apps/help"
        app.mkdir(parents=True)
        (app / "Containerfile").write_text("FROM scratch\n")
        result, calls = self.helper("build-images.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            calls,
            [
                [
                    "build",
                    "-t",
                    "localhost/myproduct-help:1.2.3",
                    "-f",
                    "apps/help/Containerfile",
                    "apps/help",
                ]
            ],
        )
        self.log.unlink()
        result, calls = self.helper("pull-images.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(calls)

    def test_registry_only_manifests_never_build(self):
        """Skip demo builds and pull exact sorted registry names, including localhost:port."""
        images = ["registry.example.test/app:2", "localhost:5000/app:1"]
        self.manifest(images)
        result, calls = self.helper("build-images.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(calls)
        result, calls = self.helper("pull-images.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            calls, [["pull", "--policy=always", image] for image in sorted(images)]
        )

    def test_postgres_demo_source_tag_follows_manifest(self):
        """Prepare the local PostgreSQL demo alias from the exact manifest tag."""
        self.manifest(["localhost/myproduct-postgres:17.11"])
        result, calls = self.helper("build-images.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            calls,
            [
                ["pull", "--policy=always", "docker.io/library/postgres:17.11"],
                [
                    "tag",
                    "docker.io/library/postgres:17.11",
                    "localhost/myproduct-postgres:17.11",
                ],
            ],
        )

    def test_pull_failure_has_no_build_fallback_or_credential_output(self):
        """Fail the pull helper without echoing private registry diagnostics."""
        self.manifest(["registry.example.test/app:2"])
        self.env["FAIL_PULL"] = "1"
        result, calls = self.helper("pull-images.sh")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            calls, [["pull", "--policy=always", "registry.example.test/app:2"]]
        )
        self.assertIn("podman login", result.stderr)
        self.assertNotIn("private-auth-token", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
