"""Release RPMs from real bundles, built with rpmbuild (backlog 69 WP1).

Skipped where rpmbuild is not installed. Only Podman is stubbed; rpmbuild and
rpm run for real, and the erase guard is executed from the built package.
"""

import copy
import os
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
        product: dict = copy.deepcopy(WORKER)
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
        (rpm,) = rpms.build(["worker"])
        self.assertEqual(rpm.name, "cedar-worker-1.2.3-1.2.3-1.noarch.rpm")
        self.assertEqual(
            rpm_query(rpm, "--queryformat", "%{NAME} %{VERSION} %{RELEASE} %{ARCH}"),
            "cedar-worker-1.2.3 1.2.3 1 noarch",
        )
        # zstd level 3, whatever the build machine's default is.
        self.assertEqual(
            rpm_query(rpm, "--queryformat", "%{PAYLOADCOMPRESSOR} %{PAYLOADFLAGS}"),
            "zstd 3",
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

    def guard(self, rpm, remaining, authorization=None, keep=None):
        """Run the package's %preun with a temporary /run/cedar.

        The guard requires a root-owned authorization; the test user owns it
        here, so only that one comparison names the test user's UID. keep, if
        given, receives whether the authorization still exists afterwards.
        """
        script = rpm_query(rpm, "--queryformat", "%{PREUN}")
        owner = '"$(stat -c %u "$auth")" = 0'
        self.assertIn(owner, script)
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory, "erase-authorization")
            if authorization is not None:
                record.write_text(authorization)
            script = script.replace("/run/cedar", directory).replace(
                owner, f'"$(stat -c %u "$auth")" = {os.getuid()}'
            )
            result = RUN(
                ["sh", "-c", script, "preun", str(remaining)],
                capture_output=True,
                text=True,
                check=False,
            )
            if keep is not None:
                keep.append(record.exists())
            return result

    def test_erase_needs_a_live_authorization_for_exactly_this_package(self):
        (rpm,) = rpms.build(["worker"])
        name = "cedar-worker-1.2.3-1.2.3-1"
        started = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19]
        live = f"{name} {os.getpid()} {started}\n"
        refused = self.guard(rpm, 0)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("use: sudo cedar-admin", refused.stderr)
        # A finished process: its PID no longer names the author.
        dead = subprocess.Popen(["true"])
        dead.wait()
        for authorization in (
            live.replace(name, "cedar-worker-1.2.4-1.2.4-1"),
            f"{name}\n",
            f"{name} {dead.pid} {started}\n",
            f"{name} {os.getpid()} {int(started) + 1}\n",
            f"{name} {os.getpid()} {started} extra\n",
        ):
            with self.subTest(authorization=authorization):
                self.assertEqual(self.guard(rpm, 0, authorization).returncode, 1)
        kept = []
        self.assertEqual(self.guard(rpm, 0, live, keep=kept).returncode, 0)
        self.assertEqual(kept, [False])  # consumed: a second erase finds nothing
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


class EnvironmentRpmTests(ProductFixture):
    """--environment takes the bundles of dist/<environment>/ (backlog 84).

    rpmbuild is replaced: this checks which archive is wrapped and where the
    package goes, not the package itself (ReleaseRpmTests).
    """

    def setUp(self):
        super().setUp()
        self.product_name = "cedar"
        product: dict = copy.deepcopy(WORKER)
        product["worker"]["env"] = {"main": {"MODE": "common"}}
        self.write_product(product, version="1.2.3")
        (self.source / "config").mkdir()
        (self.source / "config/prod1.yaml").write_text(
            "overrides:\n  worker:\n    ENVIRONMENT:\n      main:\n        MODE: prod1\n"
        )
        self.stack.enter_context(
            mock.patch.multiple(rpms, ROOT=self.source, DIST=self.source / "dist")
        )
        self.stack.enter_context(
            mock.patch.object(rpms.shutil, "which", return_value="/usr/bin/rpmbuild")
        )
        self.wrapped = []

        def build_rpm(archive, product, component, version, target):
            self.wrapped.append((archive, target))
            return target / f"{product}-{component}.rpm"

        self.stack.enter_context(mock.patch.object(rpms, "build_rpm", build_rpm))

    def test_the_environment_is_given_once_in_either_spelling(self):
        for repeated in (
            ["--environment=prod1", "--environment=prod2"],
            ["--environment", "prod1", "--environment=prod2"],
        ):
            with self.subTest(repeated=repeated):
                self.assertEqual(rpms.main(repeated), 2)
        self.assertIn(
            "ERROR: --environment given more than once", self.stderr.getvalue()
        )
        self.assertEqual(self.wrapped, [])

    def test_the_environment_directory_is_read_and_written(self):
        self.build_and_unpack("prod1")
        dist = self.source / "dist"
        rpms.build(["worker"], environment_name="prod1")
        self.assertEqual(
            self.wrapped,
            [(dist / "prod1/cedar-worker-1.2.3-offline.tar.gz", dist / "prod1/rpm")],
        )
        # The common build's archive is never taken for an environment.
        self.build_and_unpack()
        (dist / "prod1/cedar-worker-1.2.3-offline.tar.gz").unlink()
        with self.assertRaisesRegex(
            rpms.RpmError,
            "Missing dist/prod1/cedar-worker-1.2.3-offline.tar.gz; run "
            "./build-bundle.sh --environment prod1 worker",
        ):
            rpms.build(["worker"], environment_name="prod1")
        with self.assertRaisesRegex(
            catalog.common.DeployError, "missing file config/prod2.yaml"
        ):
            rpms.build(["worker"], environment_name="prod2")
