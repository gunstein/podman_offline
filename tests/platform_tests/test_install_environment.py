"""Install's account, runtime and image checks, and the order of its writes."""

import os
import runpy
import stat
import subprocess
from pathlib import Path
from unittest import mock

import yaml
from deployment import catalog, cli, common, deploy
from deployment import render as rendering

from helpers.product_fixture import ProductFixture, pod

APP = {
    "app": {
        "defaults": {
            "VOLUME_FILES": {"app-uploads": [{"component_file": "message.txt"}]},
        },
        "manifests": [
            pod(
                "app-web",
                "localhost/app:1",
                volumes=["pvc:app-uploads"],
                initContainers=[
                    {
                        "name": "init",
                        "image": "localhost/init:1",
                        "imagePullPolicy": "Never",
                    }
                ],
            )
        ],
        "files": {"message.txt": "hello\n"},
    }
}


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


class InstallEnvironmentTests(ProductFixture):
    def setUp(self):
        super().setUp()
        self.write_product(APP)
        self.release = self.build_and_unpack()["app"]
        self.use_root(self.release)
        deploy.init_config("app")
        self.config_path, self.archives, self.output, self.kube = (
            catalog.component_paths("app")
        )
        self.process.reset_mock()

    def fail_on(self, prefix, returncode=1):
        """Fail the first host command that starts with prefix."""

        def command(arguments, **kwargs):
            args = list(map(str, arguments))
            if args[: len(prefix)] == prefix:
                raise subprocess.CalledProcessError(returncode, args)
            return self.host_command(arguments, **kwargs)

        self.process.side_effect = command

    def install_fails(self):
        with mock.patch.object(cli.sys, "argv", ["deploy.sh", "install"]):
            self.assertEqual(cli.main(), 1)
        self.assertNotIn("Traceback", self.stderr.getvalue())
        return self.stderr.getvalue()

    def test_root_check_precedes_reads_writes_and_commands(self):
        self.euid.return_value = 0
        render = self.stack.enter_context(mock.patch.object(rendering, "materialize"))
        with self.assertRaisesRegex(common.DeployError, "not as root"):
            deploy.install()
        render.assert_not_called()
        self.process.assert_not_called()
        self.assertFalse(common.QUADLET_DIR.exists())

    def test_missing_persistent_config_names_expected_path(self):
        self.config_path.unlink()
        with self.assertRaises(common.DeployError) as failure:
            deploy.install()
        self.assertIn(str(self.config_path), str(failure.exception))
        self.process.assert_not_called()

    def test_paths_follow_user_database_even_when_home_differs(self):
        home = self.root / "other-service-user"
        environment = mock.patch.dict(os.environ, {"HOME": str(self.root / "operator")})
        lookup = mock.patch.object(
            common.pwd, "getpwuid", return_value=mock.Mock(pw_dir=str(home))
        )
        with environment, lookup as account:
            module = runpy.run_path(common.__file__, run_name="rootless_paths_test")
        account.assert_called_once_with(os.getuid())
        self.assertEqual(module["HOME"], home)
        # Production paths come only from layout.select(), never from the home.
        for name in ("STATE", "QUADLET_DIR", "FILES_DIR"):
            self.assertIsNone(module[name])

    def test_mismatched_home_is_refused_before_any_action(self):
        render = self.stack.enter_context(mock.patch.object(rendering, "materialize"))
        with mock.patch.dict(os.environ, {"HOME": str(self.root / "operator")}):
            with self.assertRaisesRegex(
                common.DeployError, "HOME=.*differs.*user database"
            ) as failure:
                deploy.install()
        self.assertIn(str(common.HOME), str(failure.exception))
        render.assert_not_called()
        self.process.assert_not_called()
        self.assertFalse(common.QUADLET_DIR.exists())

    def test_absent_home_uses_the_user_database(self):
        os.environ.pop("HOME", None)
        deploy.install()
        self.assertTrue(self.output.is_file())

    def test_runtime_fallback_reaches_subprocesses(self):
        os.environ.pop("XDG_RUNTIME_DIR", None)
        seen = []

        def command(arguments, **kwargs):
            seen.append(os.environ.get("XDG_RUNTIME_DIR"))
            return self.host_command(arguments, **kwargs)

        self.process.side_effect = command
        deploy.install()
        self.assertTrue(seen)
        self.assertEqual(set(seen), {"/run/user/1000"})

    def test_missing_runtime_stops_before_render_and_commands(self):
        render = self.stack.enter_context(mock.patch.object(rendering, "materialize"))
        with mock.patch.object(Path, "is_dir", return_value=False):
            with self.assertRaisesRegex(
                common.DeployError, "runtime directory.*linger"
            ):
                deploy.install()
        render.assert_not_called()
        self.process.assert_not_called()
        self.assertFalse(common.QUADLET_DIR.exists())

    def test_foreign_runtime_is_refused_before_any_action(self):
        render = self.stack.enter_context(mock.patch.object(rendering, "materialize"))
        for configured in ("/run/user/0", "/run/user/2000", "", str(self.root / "x")):
            with self.subTest(runtime=configured):
                os.environ["XDG_RUNTIME_DIR"] = configured
                with self.assertRaisesRegex(
                    common.DeployError, "XDG_RUNTIME_DIR=.*expected /run/user/1000"
                ) as error:
                    deploy.install()
                self.assertIn(repr(configured), str(error.exception))
        render.assert_not_called()
        self.process.assert_not_called()

    def test_images_load_before_archives_and_quadlet_files(self):
        archive = self.archives / "app-uploads.tar"
        events = []

        def command(arguments, **kwargs):
            args = list(map(str, arguments))
            events.append(args)
            if args[:2] in (["podman", "load"], ["podman", "image"]):
                self.assertFalse(archive.exists())
                self.assertFalse(self.output.exists())
            if args[:3] == ["systemctl", "--user", "restart"]:
                self.assertTrue(archive.exists())
                self.assertTrue(self.output.exists())
            return self.host_command(arguments, **kwargs)

        self.process.side_effect = command
        deploy.install()
        load = events.index(
            ["podman", "load", "-i", str(self.release / "images/images.tar")]
        )
        checks = [
            events.index(["podman", "image", "exists", image])
            for image in ("localhost/app:1", "localhost/init:1")
        ]
        restart = events.index(
            ["systemctl", "--user", "restart", "myproduct-app.service"]
        )
        self.assertLess(load, min(checks))
        self.assertLess(max(checks), restart)
        for path, expected in (
            (self.output, 0o600),
            (self.kube, 0o644),
            (common.QUADLET_DIR / "myproduct.network", 0o644),
            (archive, 0o600),
        ):
            self.assertEqual(mode(path), expected, path)
        docs = list(yaml.safe_load_all(self.output.read_text()))
        claim = next(doc for doc in docs if doc["kind"] == "PersistentVolumeClaim")
        self.assertEqual(
            claim["metadata"]["annotations"][common.IMPORT_SOURCE], str(archive)
        )

    def test_failed_restart_returns_one_with_hints(self):
        self.fail_on(["systemctl", "--user", "restart"])
        errors = self.install_fails()
        self.assertIn("journalctl --user -u myproduct-app.service", errors)
        self.assertIn("podman-user-generator --dryrun", errors)

    def test_missing_archive_stops_before_any_command(self):
        (self.release / "images/images.tar").unlink()
        errors = self.install_fails()
        self.assertIn("Missing image archive", errors)
        self.assertIn("images.tar", errors)
        self.process.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_missing_image_is_named_and_keeps_old_files(self):
        common.QUADLET_DIR.mkdir(parents=True)
        self.output.write_text("old yaml")
        self.kube.write_text("old kube")
        self.archives.mkdir(parents=True, exist_ok=True)
        archive = self.archives / "app-uploads.tar"
        archive.write_bytes(b"previous archive")
        for image in ("localhost/app:1", "localhost/init:1"):
            with self.subTest(image=image):
                self.fail_on(["podman", "image", "exists", image], 125)
                self.stderr.truncate(0)
                self.stderr.seek(0)
                self.assertIn(image, self.install_fails())
                self.assertEqual(self.output.read_text(), "old yaml")
                self.assertEqual(self.kube.read_text(), "old kube")
                self.assertEqual(archive.read_bytes(), b"previous archive")
        self.fail_on(["podman", "load"])
        self.install_fails()
        self.assertEqual(archive.read_bytes(), b"previous archive")


class PrepareTests(ProductFixture):
    def setUp(self):
        super().setUp()
        self.write_product(APP)

    def test_prepare_writes_private_yaml_and_archives(self):
        deploy.prepare()
        output = common.BUILD / "install.yaml"
        self.assertEqual(mode(output), 0o600)
        archive = common.BUILD / "dev/app/files/app-uploads.tar"
        self.assertEqual(mode(archive), 0o600)
        claim = next(
            doc
            for doc in yaml.safe_load_all(output.read_text())
            if doc["kind"] == "PersistentVolumeClaim"
        )
        self.assertEqual(
            claim["metadata"]["annotations"][common.IMPORT_SOURCE], str(archive)
        )
        self.process.assert_not_called()
        output.chmod(0o666)
        deploy.prepare()
        self.assertEqual(mode(output), 0o600)

    def test_prepare_exit_codes_and_result_lines(self):
        self.assertEqual(cli.main(["prepare"]), 0)
        self.assertTrue(
            self.stdout.getvalue().endswith("PASS: ./deploy.sh prepare completed\n")
        )
        defaults = self.source / "components/app/config.defaults.yaml"
        defaults.write_text(defaults.read_text() + "HTTPS_PORT: invalid\n")
        self.stdout.truncate(0)
        self.stdout.seek(0)
        self.assertEqual(cli.main(["prepare"]), 1)
        self.assertNotIn("PASS:", self.stdout.getvalue())
        self.assertIn("ERROR: ", self.stderr.getvalue())

    def test_prepare_and_install_need_their_own_layout(self):
        with self.assertRaisesRegex(
            common.DeployError, "Run install from an unpacked component bundle"
        ):
            deploy.install()
        self.use_root(self.root / "empty")
        with self.assertRaisesRegex(
            common.DeployError, "Run prepare from the source checkout"
        ):
            deploy.prepare()
