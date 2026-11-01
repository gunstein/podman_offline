"""Release RPMs from real bundles, built with rpmbuild (backlog 69 WP1).

Skipped where rpmbuild is not installed. Only Podman is stubbed; rpmbuild and
rpm run for real, and the erase guard is executed from the built package.
"""

import copy
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import rpms
from deployment import catalog

from helpers.product_fixture import WORKER, ProductFixture

# The real function: ProductFixture replaces subprocess.run with a recorder.
RUN = subprocess.run


def rpm_query(path, *args):
    return RUN(
        ["rpm", "-qp", *args, str(path)], capture_output=True, text=True, check=True
    ).stdout


@unittest.skipUnless(shutil.which("rpmbuild"), "rpmbuild is not installed")
class ReleaseRpmTests(ProductFixture):
    def setUp(self):
        super().setUp()
        self.product_name = "cedar"
        product = copy.deepcopy(WORKER)
        product["worker"]["files"] = {"notes.txt": "public\n"}
        self.write_product(product, version="1.2.3")
        self.build_and_unpack()
        self.stack.enter_context(
            mock.patch.multiple(rpms, ROOT=self.source, DIST=self.source / "dist")
        )
        recorded = self.process.side_effect

        def command(arguments, **kwargs):
            if arguments[0] == "rpmbuild":
                return RUN(arguments, **kwargs)
            return recorded(arguments, **kwargs)

        self.process.side_effect = command

    def test_one_side_by_side_package_with_the_unchanged_release(self):
        (rpm,) = rpms.build()
        self.assertEqual(rpm.name, "cedar-worker-1.2.3-1.2.3-1.noarch.rpm")
        self.assertEqual(
            rpm_query(rpm, "--queryformat", "%{NAME} %{VERSION} %{RELEASE} %{ARCH}"),
            "cedar-worker-1.2.3 1.2.3 1 noarch",
        )
        # No generated dependencies; nothing owned outside the release tree.
        self.assertNotIn("python", rpm_query(rpm, "--requires"))
        root = "/var/lib/cedar/releases/cedar-worker-1.2.3"
        listing = rpm_query(
            rpm, "--queryformat", "[%{FILEMODES:perms} %{FILEUSERNAME} %{FILENAMES}\n]"
        )
        paths = {line.split()[2]: line.split()[:2] for line in listing.splitlines()}
        self.assertTrue(all(path.startswith(root) for path in paths))
        self.assertEqual(paths[root], ["drwxr-xr-x", "root"])
        self.assertEqual(paths[root + "/deploy.sh"], ["-rwxr-xr-x", "root"])
        self.assertEqual(paths[root + "/bundle.yaml"], ["-rw-r--r--", "root"])
        self.assertIn(root + "/components/worker/files/notes.txt", paths)
        self.assertIn(root + "/checksums.sha256", paths)

    def guard(self, rpm, remaining, authorization=None):
        """Run the package's %preun with a temporary /run/cedar."""
        script = rpm_query(rpm, "--queryformat", "%{PREUN}")
        with tempfile.TemporaryDirectory() as directory:
            if authorization is not None:
                Path(directory, "erase-authorization").write_text(authorization)
            script = script.replace("/run/cedar", directory)
            return RUN(
                ["sh", "-c", script, "preun", str(remaining)],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_erase_needs_the_authorization_for_exactly_this_package(self):
        (rpm,) = rpms.build()
        name = "cedar-worker-1.2.3-1.2.3-1"
        refused = self.guard(rpm, 0)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("use: sudo cedar-admin", refused.stderr)
        self.assertEqual(self.guard(rpm, 0, "cedar-worker-1.2.4-1.2.4-1").returncode, 1)
        self.assertEqual(self.guard(rpm, 0, name).returncode, 0)
        # An upgrade or reinstall leaves an instance: no authorization needed.
        self.assertEqual(self.guard(rpm, 1).returncode, 0)

    def test_a_version_is_built_once(self):
        (rpm,) = rpms.build(["worker"])
        before = rpm.read_bytes()
        with self.assertRaisesRegex(rpms.RpmError, "already exists.*new VERSION"):
            rpms.build(["worker"])
        self.assertEqual(rpm.read_bytes(), before)

    def test_a_changed_or_missing_bundle_is_refused_before_rpmbuild(self):
        descriptor = catalog.source_descriptors(self.source)["worker"]
        archive = (
            self.source
            / "dist"
            / ("cedar-worker-" + descriptor["version"] + "-offline.tar.gz")
        )
        archive.write_bytes(archive.read_bytes() + b"tampered")
        with self.assertRaisesRegex(rpms.RpmError, "does not match its .sha256"):
            rpms.build()
        archive.unlink()
        with self.assertRaisesRegex(rpms.RpmError, "run ./build-bundle.sh worker"):
            rpms.build()
        with self.assertRaisesRegex(rpms.RpmError, "Unknown component reports"):
            rpms.build(["reports"])
        self.assertFalse((self.source / "dist/rpm").exists())

    def test_main_reports_one_error_line(self):
        with mock.patch.object(rpms.shutil, "which", return_value=None):
            self.assertEqual(rpms.main([]), 1)
        self.assertIn("ERROR: rpmbuild is missing", self.stderr.getvalue())
        self.assertEqual(rpms.main([]), 0)
        self.assertIn("PASS: ./build-rpms.sh completed", self.stdout.getvalue())
