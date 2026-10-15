"""Separate platform bundles and explicit refusal of retained core layouts."""

import json
import subprocess
from unittest import mock

import yaml
from test_components import ComponentFixture

from deployment import cli, common, deploy

LEGACY_VOLUME_EXISTS = deploy.legacy_volume_exists


class PlatformSafetyTests(ComponentFixture):
    """Exercise guards against real temporary installed state, with only host transport stubbed."""

    def snapshot(self):
        return {
            str(path.relative_to(common.HOME)): (path.read_bytes(), path.stat().st_mode)
            for path in common.HOME.rglob("*")
            if path.is_file()
        }

    def test_legacy_and_mixed_files_refuse_all_operations_without_commands(self):
        deploy.install()
        for name in (
            "core/config.yaml",
            "installed/core",
            ".config/containers/systemd/myproduct-core.yaml",
            ".config/containers/systemd/myproduct-core.kube",
            ".config/systemd/user/myproduct-core.service",
        ):
            for operation in (
                lambda: deploy.init_config("app1"),
                deploy.install,
                deploy.uninstall,
            ):
                with self.subTest(path=name, operation=operation):
                    path = self.write("home/" + name, "legacy retained state")
                    before = self.snapshot()
                    self.process.reset_mock()
                    with self.assertRaisesRegex(
                        common.DeployError, "Legacy core layout.*migration"
                    ):
                        operation()
                    self.process.assert_not_called()
                    self.assertEqual(self.snapshot(), before)
                    path.unlink()
                    if name.startswith("core/"):
                        path.parent.rmdir()

    def test_leftover_core_directory_or_broken_alias_is_not_treated_as_absent(self):
        old = common.HOME / "core"
        old.mkdir()
        for alias in (False, True):
            with self.subTest(alias=alias):
                if alias:
                    old.rmdir()
                    old.symlink_to(self.root / "missing")
                before = self.snapshot()
                with self.assertRaisesRegex(common.DeployError, "Legacy core layout"):
                    deploy.install()
                self.assertEqual(self.snapshot(), before)
        old.unlink()

    def test_old_database_volumes_without_marker_refuse_before_generation_or_images(
        self,
    ):
        deploy.install()
        for volume in (
            "core-identity-data",
            "core-identity-protection",
            "core-routes",
            "core-clients",
        ):
            for operation in (
                lambda: deploy.init_config("app1"),
                deploy.install,
                deploy.uninstall,
            ):
                with self.subTest(volume=volume, operation=operation):

                    def command(args, volume=volume, **kwargs):
                        self.assertEqual(args[:3], ["podman", "volume", "exists"])
                        return subprocess.CompletedProcess(
                            args, 0 if args[-1] == volume else 1
                        )

                    before = self.snapshot()
                    self.process.reset_mock()
                    self.process.side_effect = command
                    transport = mock.patch.object(
                        deploy, "legacy_volume_exists", side_effect=LEGACY_VOLUME_EXISTS
                    )
                    refusal = self.assertRaisesRegex(
                        common.DeployError, "Legacy core volume.*migration"
                    )
                    with transport, refusal:
                        operation()
                    self.assertEqual(self.snapshot(), before)
                    self.assertEqual(
                        self.process.call_args_list[-1].args[0][-1], volume
                    )

    def test_legacy_volume_check_errors_refuse_without_exposing_transport_output(self):
        for result in (
            subprocess.CompletedProcess(
                [], 125, stdout=b"sensitive", stderr=b"sensitive"
            ),
            FileNotFoundError("private"),
            subprocess.TimeoutExpired("private", 30),
        ):
            with self.subTest(result=result):
                self.process.reset_mock()
                self.process.side_effect = (
                    result if isinstance(result, Exception) else None
                )
                self.process.return_value = result
                before = self.snapshot()
                transport = mock.patch.object(
                    deploy, "legacy_volume_exists", side_effect=LEGACY_VOLUME_EXISTS
                )
                refusal = self.assertRaisesRegex(
                    common.DeployError, "Cannot check legacy core"
                )
                with transport, refusal as caught:
                    deploy.install()
                self.assertNotIn("sensitive", str(caught.exception))
                self.assertNotIn("private", str(caught.exception))
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.process.call_count, 1)

    def test_apps_never_embed_platform_and_missing_dependency_writes_nothing(self):
        for name in ("app1", "app2", "help"):
            with self.subTest(component=name):
                self.component_manifest(name)
                self.write(
                    "home/" + name + "/config.yaml",
                    "PUBLIC_ORIGIN: https://example.test:8443\nHTTPS_PORT: 8443\n",
                )
                self.select(name)
                self.assertEqual(deploy.bundle_components(), [name])
                marker = common.HOME / "installed/platform"
                if marker.exists():
                    marker.unlink()
                before = self.snapshot()
                self.process.reset_mock()
                with self.assertRaisesRegex(
                    common.DeployError, "separate platform bundle"
                ):
                    deploy.install()
                self.process.assert_not_called()
                self.assertEqual(self.snapshot(), before)
        self.write("bundle.yaml", "name: app1\ncomponents: [platform, app1]\n")
        with self.assertRaisesRegex(common.DeployError, "platform must be separate"):
            deploy.bundle_components()

    def test_installed_dependency_ranges_survive_removed_release_and_reject_incompatible_platform(
        self,
    ):
        deploy.install()
        requirement = common.HOME / "dependencies/app1.json"
        self.assertEqual(
            json.loads(requirement.read_text()),
            {
                "platform": {"min": "1.0.0", "before": "2.0.0"},
                "identity": {"min": "1.0.0", "before": "2.0.0"},
            },
        )
        self.select("platform")
        self.write("PLATFORM_VERSION", "2.0.0\n")
        before = self.snapshot()
        self.process.reset_mock()
        with self.assertRaisesRegex(common.DeployError, "dependency for identity"):
            deploy.install()
        self.process.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        requirement.unlink()
        self.write("PLATFORM_VERSION", "1.1.0\n")
        with self.assertRaisesRegex(
            common.DeployError, "installed platform requirement"
        ):
            deploy.install()
        self.process.assert_not_called()

    def test_platform_data_deletion_targets_only_its_renamed_volume(self):
        self.select("platform")
        self.write("PLATFORM_VERSION", "1.1.0\n")
        path = self.root / "components/platform/manifests/10-pod.yaml"
        pod = yaml.safe_load(path.read_text())
        pod["spec"]["volumes"] = [
            {
                "name": "data",
                "persistentVolumeClaim": {"claimName": "platform-routes"},
            }
        ]
        path.write_text(
            yaml.safe_dump_all(
                [
                    {
                        "kind": "PersistentVolumeClaim",
                        "metadata": {"name": "platform-routes"},
                    },
                    pod,
                ]
            )
        )
        deploy.install()
        (common.HOME / "installed/identity").unlink()
        sibling = (common.HOME / "app1/config.yaml").read_bytes()
        self.process.reset_mock()
        self.process.return_value = subprocess.CompletedProcess([], 0)
        deploy.uninstall("platform", delete_data=True)
        removals = [
            call.args[0]
            for call in self.process.call_args_list
            if call.args[0][:3] == ["podman", "volume", "rm"]
        ]
        self.assertEqual(removals, [["podman", "volume", "rm", "platform-routes"]])
        self.assertEqual((common.HOME / "app1/config.yaml").read_bytes(), sibling)
        self.assertFalse((common.HOME / "platform").exists())
        self.assertTrue((common.QUADLET_DIR / "myproduct.network").exists())

    def test_old_cli_arguments_refuse_before_any_operation(self):
        for arguments in (
            ["init-config", "core"],
            ["uninstall", "core", "--delete-data"],
        ):
            command_line = mock.patch.object(cli.sys, "argv", ["deploy"] + arguments)
            with self.subTest(arguments=arguments), command_line:
                before = self.snapshot()
                self.process.reset_mock()
                self.assertEqual(cli.main(), 2)
                self.process.assert_not_called()
                self.assertEqual(self.snapshot(), before)
        self.assertIn("renamed to platform", self.stderr.getvalue())
