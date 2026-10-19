"""Test manifest-driven dev build and pull helpers with a recording Podman stub."""

import unittest
from pathlib import Path

from helpers.image_fixture import ImageHelperFixture

ROOT = Path(__file__).resolve().parents[2]


class ImageHelperTests(ImageHelperFixture):
    """Exercise the actual shell helpers without Podman, networking or registry credentials."""

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
