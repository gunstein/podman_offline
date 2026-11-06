"""The lab's release builders on the real product, with only git and Podman stubbed (backlog 78).

The help, identity and platform upgrade builders in remote.sh (HELP_BUILD) edit
a checkout of the product and build one bundle. They change VERSION, never a
manifest: help and identity tag their image @@COMPONENT_VERSION@@ (backlog 63). These tests run that code on a
copy of the files Git tracks, so a builder that no longer fits the product's
manifests, catalog or bundle format fails here instead of in the lab.
"""

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import renamed_product
import test_acceptance as base
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # bundle.py lives at the repository root.

import bundle
from deployment import catalog

HELP_BUILD = base.shell_code(
    Path(__file__).with_name("remote.sh").read_text(), heredoc="HELP_BUILD"
)


class ReleaseBuilderTests(unittest.TestCase):
    def build(self, kind, version="9.9.9"):
        """Run HELP_BUILD for one kind; return (release tree, podman builds)."""
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        source = directory / "source"
        renamed_product.copy_tracked_files(ROOT, source)
        builds = []

        def command(args, **kwargs):
            args = list(map(str, args))
            if args[:2] == ["git", "clone"]:
                shutil.copytree(source, Path(args[-1]))
            elif args[:1] == ["git"] and args[3:5] == ["checkout", "-q"]:
                pass  # The copy is already the tested revision.
            elif args[:2] == ["podman", "build"]:
                context = Path(args[-1])
                code = "".join(
                    (context / name).read_text()
                    for name in ("Program.cs", "index.html")
                    if (context / name).is_file()
                )
                builds.append((args, code))
            elif args[:2] == ["podman", "pull"]:
                pass
            elif args[:2] == ["podman", "save"]:
                Path(args[args.index("-o") + 1]).write_bytes(b"stub images")
            else:
                raise AssertionError("Unexpected external command: " + str(args))
            return subprocess.CompletedProcess(args, 0, b"", b"")

        with (
            mock.patch.object(Path, "cwd", return_value=source),
            mock.patch.object(subprocess, "run", side_effect=command),
            mock.patch.multiple(
                bundle, ROOT=source, STAGE=source / "unused", DIST=source / "dist"
            ),
            mock.patch.dict(
                os.environ,
                HELP_RELEASE_VERSION=version,
                RELEASE_KIND=kind,
                SOURCE_REVISION="f" * 40,
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            exec(compile(HELP_BUILD, "HELP_BUILD", "exec"), {})  # noqa: S102 - repository action under test
        product = catalog.product_name(source)
        archive = source / "dist" / f"{product}-{kind}-{version}-offline.tar.gz"
        with tarfile.open(str(archive)) as tar:
            tar.extractall(str(directory / "release"), filter="data")
        return directory / "release" / f"{product}-{kind}-{version}", builds

    def check_release(self, release, kind, version):
        """The built release is a valid bundle whose images match its manifests."""
        descriptor = catalog.load_bundle_descriptor(release)
        self.assertEqual((descriptor["name"], descriptor["version"]), (kind, version))
        images = (release / "images/images.txt").read_text().split()
        self.assertEqual(
            images, bundle.manifest_images(release / "components" / kind / "manifests")
        )
        self.assertFalse(any("@@" in image for image in images))
        return images

    def test_help_and_identity_builders_tag_the_new_image_and_build_one_bundle(self):
        for kind, image, marker in (
            ("help", "localhost/demo-help:", "<p>help-release-9.9.9</p>"),
            ("identity", "localhost/demo-identity:", 'release = "9.9.9"'),
        ):
            with self.subTest(kind=kind):
                release, builds = self.build(kind)
                images = self.check_release(release, kind, "9.9.9")
                self.assertIn(image + "9.9.9", images)
                self.assertEqual(len(builds), 1)
                arguments, code = builds[0]
                self.assertIn(image + "9.9.9", arguments)
                self.assertIn(marker, code)  # The built application changed.
                self.assertEqual(
                    sorted(p.name for p in (release / "components").iterdir()), [kind]
                )

    def test_platform_builder_changes_only_the_version(self):
        release, builds = self.build("platform")
        self.check_release(release, "platform", "9.9.9")
        self.assertEqual(builds, [])
        source_images = bundle.manifest_images(ROOT / "components/platform/manifests")
        self.assertEqual(
            (release / "images/images.txt").read_text().split(), source_images
        )
        self.assertEqual(
            yaml.safe_load((release / "bundle.yaml").read_text())["version"], "9.9.9"
        )


class ExpectedImageTests(unittest.TestCase):
    """help-upgrade/identity-upgrade: the installed YAML names the new VERSION's image."""

    def run_check(self, image):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        units = directory / "config/containers/systemd"
        units.mkdir(parents=True)
        (units / "myproduct-help.yaml").write_text(
            "kind: Pod\nmetadata: {name: help}\nspec:\n"
            "  containers: [{name: web, image: 'localhost/demo-help:9.9.9'}]\n"
        )
        script = (
            'as_product() { "$@"; }\n'
            + base.shell_code(
                Path(__file__).with_name("remote.sh").read_text(),
                function="expected_image",
            )
            + '\nexpected_image "$1"\n'
        )
        return subprocess.run(
            ["bash", "-c", script, "-", image],
            env=dict(
                os.environ,
                install_root=str(directory),
                product_name="myproduct",
                bundle="help",
            ),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_new_version_image_passes_and_old_one_fails(self):
        result = self.run_check("localhost/demo-help:9.9.9")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS: the installed YAML names", result.stdout)
        result = self.run_check("localhost/demo-help:9.9.8")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL: the installed YAML does not name", result.stderr)


if __name__ == "__main__":
    unittest.main()
