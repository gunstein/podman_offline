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

ROOT = Path(__file__).resolve().parents[2]


class ImageHelperFixture(unittest.TestCase):
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
        result = subprocess.run(
            ["bash", str(self.root / "dev" / name)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=False,
            env=self.env,
        )
        calls = (
            [json.loads(line) for line in self.log.read_text().splitlines()]
            if self.log.exists()
            else []
        )
        return result, calls
