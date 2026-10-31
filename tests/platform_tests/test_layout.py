"""Production paths outside the login home: bootstrap file and root checks (backlog 64)."""

import contextlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deployment import common, deploy, layout, validation

# A product name that differs from the account and from the shipped demo.
PRODUCT = "orders"


class NonRootOs:
    """os for deploy.py only: a non-root effective UID, everything else real."""

    def __init__(self, uid):
        self.uid = uid

    def geteuid(self):
        return self.uid

    def __getattr__(self, name):
        return getattr(os, name)


class LayoutFixture(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.home = self.root / "home/operator-account"
        self.home.mkdir(parents=True)
        self.anchor = self.root / "var-lib"
        self.install = self.anchor / PRODUCT
        self.install.mkdir(parents=True, mode=0o755)
        os.chmod(str(self.anchor), 0o755)
        for name in ("state", "config", "storage"):
            (self.install / name).mkdir(mode=0o700)
        for name, value in {
            "HOME": self.home,
            "STATE": None,
            "QUADLET_DIR": None,
            "FILES_DIR": None,
        }.items():
            self.stack.enter_context(mock.patch.object(common, name, value))
        for name, value in {
            "ANCHOR": self.anchor,
            "TRUSTED_TOP": self.root,
            "ROOT_UID": os.geteuid(),
        }.items():
            self.stack.enter_context(mock.patch.object(layout, name, value))
        self.stack.enter_context(mock.patch.dict(os.environ))
        for name in layout.DIRECTORIES:
            os.environ.pop(name, None)
        self.path = self.home / ".orders/orders.env"

    def bootstrap(self, text, mode=0o600):
        self.path.parent.mkdir(mode=0o700, exist_ok=True)
        self.path.write_text(text)
        self.path.chmod(mode)

    def valid(self):
        self.bootstrap("INSTALL_ROOT=" + str(self.install) + "\n")

    def assertUnselected(self):
        self.assertIsNone(common.STATE)
        self.assertIsNone(common.QUADLET_DIR)
        for name in layout.DIRECTORIES:
            self.assertNotIn(name, os.environ)


class BootstrapTests(LayoutFixture):
    def test_select_assigns_every_production_path_from_the_root(self):
        self.bootstrap(
            '# settings\n\nAPP_MODE=fast\nINSTALL_ROOT="' + str(self.install) + '"\n'
        )
        self.assertEqual(layout.select(PRODUCT), self.install)
        self.assertEqual(common.STATE, self.install / "state")
        self.assertEqual(common.FILES_DIR, self.install / "state/files")
        self.assertEqual(common.QUADLET_DIR, self.install / "config/containers/systemd")
        self.assertEqual(os.environ["XDG_CONFIG_HOME"], str(self.install / "config"))
        self.assertEqual(os.environ["XDG_DATA_HOME"], str(self.install / "storage"))
        # Application settings in the same file are not exported.
        self.assertNotIn("APP_MODE", os.environ)
        # The identity home is unchanged.
        self.assertEqual(common.HOME, self.home)

    def test_missing_file_names_the_file_and_the_required_line(self):
        with self.assertRaisesRegex(
            common.DeployError, "Missing .*orders.env.*INSTALL_ROOT=.*var-lib/orders"
        ):
            layout.select(PRODUCT)
        self.assertUnselected()

    def test_invalid_lines_name_the_line_never_the_value(self):
        cases = {
            "not a pair SECRET-VALUE\n": "line 1: expected KEY=VALUE",
            "export INSTALL_ROOT=SECRET-VALUE\n": "line 1: expected KEY=VALUE",
            "INSTALL_ROOT=/x\nINSTALL_ROOT=SECRET-VALUE\n": "line 2: duplicate",
            "OTHER=SECRET-VALUE\n": "missing INSTALL_ROOT",
            "INSTALL_ROOT=$(SECRET-VALUE)\n": "line 1: INSTALL_ROOT must be",
            "INSTALL_ROOT=`SECRET-VALUE`\n": "line 1: INSTALL_ROOT must be",
            "INSTALL_ROOT=" + str(self.install) + "/../SECRET-VALUE\n": "line 1",
            "INSTALL_ROOT=/var/lib/SECRET-VALUE\n": "line 1: INSTALL_ROOT must be",
        }
        for text, message in cases.items():
            with self.subTest(text=text):
                self.bootstrap(text)
                with self.assertRaisesRegex(common.DeployError, message) as failure:
                    layout.select(PRODUCT)
                self.assertNotIn("SECRET-VALUE", str(failure.exception))
                self.assertUnselected()

    def test_command_like_values_are_never_executed(self):
        marker = self.root / "executed"
        self.bootstrap(
            f"HOOK=$(touch {marker})\nOTHER=`touch {marker}`\nINSTALL_ROOT={self.install}\n"
        )
        with mock.patch.object(subprocess, "run") as run:
            layout.select(PRODUCT)
        run.assert_not_called()
        self.assertFalse(marker.exists())

    def test_private_file_and_directory_are_required(self):
        self.valid()
        self.path.chmod(0o644)
        with self.assertRaisesRegex(common.DeployError, "mode 0600"):
            layout.select(PRODUCT)
        self.path.chmod(0o600)
        self.path.parent.chmod(0o750)
        with self.assertRaisesRegex(common.DeployError, "mode 0700"):
            layout.select(PRODUCT)
        self.assertUnselected()

    def test_links_to_the_bootstrap_file_are_refused(self):
        real = self.root / "elsewhere.env"
        real.write_text("INSTALL_ROOT=" + str(self.install) + "\n")
        real.chmod(0o600)
        self.path.parent.mkdir(mode=0o700)
        self.path.symlink_to(real)
        with self.assertRaisesRegex(common.DeployError, "symlinked bootstrap"):
            layout.select(PRODUCT)
        self.path.unlink()
        os.link(str(real), str(self.path))
        with self.assertRaisesRegex(common.DeployError, "without links"):
            layout.select(PRODUCT)
        self.path.unlink()
        self.path.parent.rmdir()
        self.path.parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(common.DeployError, "directory owned by you"):
            layout.select(PRODUCT)
        self.assertUnselected()


class RootTests(LayoutFixture):
    def setUp(self):
        super().setUp()
        self.valid()

    def test_writable_or_linked_root_is_refused(self):
        self.install.chmod(0o775)
        with self.assertRaisesRegex(common.DeployError, "root-owned directory"):
            layout.select(PRODUCT)
        self.install.chmod(0o755)
        self.anchor.chmod(0o777)
        with self.assertRaisesRegex(common.DeployError, "var-lib must be"):
            layout.select(PRODUCT)
        self.anchor.chmod(0o755)
        moved = self.anchor / "moved"
        self.install.rename(moved)
        self.install.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(common.DeployError, "root-owned directory"):
            layout.select(PRODUCT)
        self.assertUnselected()

    def test_account_directories_must_be_prepared_and_private(self):
        (self.install / "storage").chmod(0o755)
        with self.assertRaisesRegex(common.DeployError, "storage must have mode 0700"):
            layout.select(PRODUCT)
        (self.install / "storage").chmod(0o700)
        (self.install / "config").rmdir()
        with self.assertRaisesRegex(
            common.DeployError, "Missing .*config.*prepare-host"
        ):
            layout.select(PRODUCT)
        (self.install / "config").symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(common.DeployError, "config must be a directory"):
            layout.select(PRODUCT)
        self.assertUnselected()


class UserManagerTests(LayoutFixture):
    def manager(self, stdout, returncode=0):
        return mock.patch.object(
            subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], returncode, stdout, ""),
        )

    def test_matching_environment_passes(self):
        text = "HOME=/x\nXDG_CONFIG_HOME={0}/config\nXDG_DATA_HOME={0}/storage\n"
        with self.manager(text.format(self.install)) as run:
            layout.check_user_manager(self.install)
        self.assertEqual(
            run.call_args[0][0], ["systemctl", "--user", "show-environment"]
        )

    def test_missing_or_different_storage_is_refused(self):
        for text in (
            "PATH=/usr/bin\n",
            "XDG_CONFIG_HOME={0}/config\nXDG_DATA_HOME=/home/x\n",
        ):
            with self.subTest(text=text):
                with self.manager(text.format(self.install)):
                    with self.assertRaisesRegex(
                        common.DeployError,
                        "user systemd manager has XDG_.*prepare-host",
                    ):
                        layout.check_user_manager(self.install)

    def test_unreadable_manager_is_refused(self):
        with self.manager("", returncode=1):
            with self.assertRaisesRegex(common.DeployError, "show-environment exit 1"):
                layout.check_user_manager(self.install)


class CommandSelectionTests(LayoutFixture):
    """Only production commands from a release read the bootstrap file."""

    def release(self, source):
        self.release_root = self.root / "release"
        (self.release_root / "components").mkdir(parents=True)
        if not source:
            (self.release_root / "bundle.yaml").write_text("")
        self.stack.enter_context(mock.patch.object(common, "ROOT", self.release_root))
        # deploy refuses root; layout compares owners with the real UID, so
        # the fixture's files stay owned by this runner (no chown needed).
        self.stack.enter_context(
            mock.patch.object(deploy, "os", NonRootOs(os.geteuid() or 1000))
        )
        os.environ["HOME"] = str(self.home)

    def test_source_checkout_never_reads_the_bootstrap_file(self):
        self.valid()
        self.release(source=True)
        with mock.patch.object(layout, "read_bootstrap") as read:
            with self.assertRaisesRegex(common.DeployError, "source checkout"):
                deploy.service_user()
            read.assert_not_called()
        self.assertUnselected()

    def test_release_selects_the_layout_of_its_product(self):
        self.valid()
        self.release(source=False)
        with mock.patch("deployment.catalog.product_name", return_value=PRODUCT):
            self.assertEqual(deploy.service_user(), self.install)
        self.assertEqual(common.STATE, self.install / "state")

    def test_source_validate_ignores_production_settings(self):
        self.valid()
        self.release(source=True)
        with mock.patch.object(layout, "select") as select, mock.patch.object(
            validation, "validate_catalog", return_value=(["x"], [])
        ):
            validation.validate()
        select.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class InitLayoutTests(LayoutFixture):
    def test_interrupted_creation_and_fresh_process_retry(self):
        helper = Path(__file__).resolve().parents[1] / "helpers/init_layout_driver.py"
        for boundary in ("created", "synced", "published"):
            with self.subTest(boundary=boundary):
                result = subprocess.run(
                    [sys.executable, "-B", str(helper), str(self.root), boundary],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=dict(os.environ, PYTHONPATH=str(helper.parents[2])),
                    check=False,
                )
                self.assertEqual(result.returncode, -9, result.stderr)
                self.assertEqual(self.path.exists(), boundary == "published")
                result = subprocess.run(
                    [sys.executable, "-B", str(helper), str(self.root), "retry"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=dict(os.environ, PYTHONPATH=str(helper.parents[2])),
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    self.path.read_text(), "INSTALL_ROOT=" + str(self.install) + "\n"
                )
                self.assertEqual(self.path.stat().st_nlink, 1)
                layout.initialize(PRODUCT)
                self.path.unlink()

    def test_concurrent_bootstrap_is_never_overwritten(self):
        publish = layout.publish_bootstrap
        content = "INSTALL_ROOT=" + str(self.install) + "\nAPP_SETTING=retained\n"

        def concurrent(directory, temporary, name):
            self.path.write_text(content)
            self.path.chmod(0o600)
            publish(directory, temporary, name)

        with mock.patch.object(layout, "publish_bootstrap", side_effect=concurrent):
            layout.initialize(PRODUCT)
        self.assertEqual(self.path.read_text(), content)
        self.assertEqual(self.path.stat().st_nlink, 1)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_initialize_is_explicit_private_and_preserves_existing_bytes(self):
        layout.initialize(PRODUCT)
        self.assertEqual(
            self.path.read_text(), "INSTALL_ROOT=" + str(self.install) + "\n"
        )
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)
        self.path.write_text(self.path.read_text() + "APP_SETTING=private-value\n")
        before = self.path.read_bytes(), self.path.stat().st_ino
        layout.initialize(PRODUCT)
        self.assertEqual((self.path.read_bytes(), self.path.stat().st_ino), before)
        self.assertUnselected()

    def test_initialize_refuses_conflict_symlink_and_missing_preparation(self):
        self.bootstrap("INSTALL_ROOT=/wrong\n")
        with self.assertRaises(common.DeployError):
            layout.initialize(PRODUCT)
        self.assertEqual(self.path.read_text(), "INSTALL_ROOT=/wrong\n")
        self.path.unlink()
        target = self.root / "target"
        target.write_text("preserve")
        self.path.symlink_to(target)
        with self.assertRaises(common.DeployError):
            layout.initialize(PRODUCT)
        self.assertEqual(target.read_text(), "preserve")
        self.path.unlink()
        (self.install / "state").rmdir()
        with self.assertRaises(common.DeployError):
            layout.initialize(PRODUCT)
        self.assertFalse(self.path.exists())
