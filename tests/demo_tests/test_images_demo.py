"""Test manifest-driven dev build and pull helpers with a recording Podman stub."""

import shutil
from pathlib import Path

from helpers.image_fixture import ImageHelperFixture

ROOT = Path(__file__).resolve().parents[2]


class DemoImageHelperTests(ImageHelperFixture):
    def test_build_uses_manifest_tag_and_pull_skips_local_images(self):
        """Build a local demo image with the manifest tag and avoid registry pulls."""
        self.manifest(["localhost/demo-help:1.2.3"])
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
                    "localhost/demo-help:1.2.3",
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

    def test_actual_product_builds_unchanged_apps_and_pulls_stock_nginx(self):
        """Exercise the existing helpers against the actual product manifest image set."""
        shutil.copytree(ROOT / "components", self.root / "components")
        for name in ("bundles.yaml",):
            shutil.copy2(ROOT / name, self.root / name)
        recipes = (
            ("help", "localhost/demo-help:0.2.0"),
            ("identity", "localhost/demo-identity:0.2.4"),
            ("todo-backend", "localhost/demo-todo-backend:0.2.2"),
            ("todo-frontend", "localhost/demo-todo-frontend:0.2.0"),
            ("whoami-backend", "localhost/demo-whoami-backend:0.1.1"),
            ("whoami-frontend", "localhost/demo-whoami-frontend:0.1.0"),
        )
        for name, _ in recipes:
            target = self.root / "apps" / name
            target.mkdir(parents=True)
            shutil.copy2(
                ROOT / "apps" / name / "Containerfile", target / "Containerfile"
            )
        result, calls = self.helper("build-images.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [call for call in calls if call[0] == "build"],
            [
                [
                    "build",
                    "-t",
                    image,
                    "-f",
                    "apps/" + name + "/Containerfile",
                    "apps/" + name,
                ]
                for name, image in recipes
            ],
        )
        self.assertEqual(
            [call for call in calls if call[0] in ("pull", "tag")],
            [
                ["pull", "--policy=always", "docker.io/library/postgres:17.11"],
                [
                    "tag",
                    "docker.io/library/postgres:17.11",
                    "localhost/demo-postgres:17.11",
                ],
            ],
        )
        self.assertFalse(
            any("proxy" in argument for call in calls for argument in call)
        )
        self.log.unlink()
        result, calls = self.helper("pull-images.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            calls, [["pull", "--policy=always", "docker.io/library/nginx:1.28-alpine"]]
        )

    def test_postgres_demo_source_tag_follows_manifest(self):
        """Prepare the local PostgreSQL demo alias from the exact manifest tag."""
        self.manifest(["localhost/demo-postgres:17.11"])
        result, calls = self.helper("build-images.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            calls,
            [
                ["pull", "--policy=always", "docker.io/library/postgres:17.11"],
                [
                    "tag",
                    "docker.io/library/postgres:17.11",
                    "localhost/demo-postgres:17.11",
                ],
            ],
        )
