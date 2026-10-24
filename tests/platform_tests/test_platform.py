"""Separate platform bundles, dependency contracts and scoped state operations."""

import json
import subprocess
from pathlib import Path
from unittest import mock

import yaml
from deployment import catalog, cli, common, deploy

from helpers.component_fixture import ComponentFixture


class PlatformSafetyTests(ComponentFixture):
    """Exercise guards against real temporary installed state, with only host transport stubbed."""

    def snapshot(self):
        return {
            str(path.relative_to(common.STATE)): (
                path.read_bytes(),
                path.stat().st_mode,
            )
            for path in common.STATE.rglob("*")
            if path.is_file()
        }

    def test_config_initialization_and_repetition_need_no_podman_volume_checks(self):
        """Initialize current defaults without generating credentials or querying old volumes."""
        repo = Path(__file__).resolve().parents[1] / "fixtures/catalog"
        for name in (
            "config/common.defaults.yaml",
            "components/app1/config.defaults.yaml",
        ):
            self.write(name, (repo / name).read_bytes())
        target = common.STATE / "app1/config.yaml"
        target.unlink()
        self.process.reset_mock()
        deploy.init_config("app1")
        before = self.snapshot()
        deploy.init_config("app1")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertFalse((common.STATE / "app1/credentials").exists())
        self.process.assert_not_called()

    def test_apps_never_embed_platform_and_missing_dependency_writes_nothing(self):
        for name in ("app1", "app2", "help"):
            with self.subTest(component=name):
                self.component_manifest(name)
                self.write(
                    "home/" + name + "/config.yaml",
                    "PUBLIC_ORIGIN: https://example.test:8443\nHTTPS_PORT: 8443\n",
                )
                self.select(name)
                self.assertEqual(deploy.bundle_descriptor()["name"], name)
                marker = common.STATE / "installed/platform"
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
        # One component per bundle: a descriptor has no component list to extend.
        descriptor = yaml.safe_load((self.root / "bundle.yaml").read_text())
        descriptor["components"] = ["platform", "app1"]
        self.write("bundle.yaml", yaml.safe_dump(descriptor))
        with self.assertRaisesRegex(common.DeployError, "expected exactly the fields"):
            deploy.bundle_descriptor()

    def test_installed_dependency_ranges_survive_removed_release_and_reject_incompatible_platform(
        self,
    ):
        deploy.install()
        requirement = common.STATE / "metadata/app1.json"
        self.assertEqual(
            json.loads(requirement.read_text())["requires"],
            {
                "platform": {"min": "1.0.0", "before": "2.0.0"},
                "identity": {"min": "1.0.0", "before": "2.0.0"},
            },
        )
        self.write("components/platform/VERSION", "2.0.0\n")
        self.select("platform")
        before = self.snapshot()
        self.process.reset_mock()
        with self.assertRaisesRegex(common.DeployError, "dependency for app1"):
            deploy.install()
        self.process.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        requirement.unlink()
        self.write("components/platform/VERSION", "1.1.0\n")
        self.select("platform")
        with self.assertRaisesRegex(
            common.DeployError, "Missing installed metadata.*app1"
        ):
            deploy.install()
        self.process.assert_not_called()

    def test_platform_data_deletion_targets_only_its_pvc_and_mounted_config_map(self):
        self.write("components/platform/VERSION", "1.1.0\n")
        self.select("platform")
        path = self.root / "components/platform/manifests/10-pod.yaml"
        pod = yaml.safe_load(path.read_text())
        pod["spec"]["volumes"] = [
            {
                "name": "data",
                "persistentVolumeClaim": {"claimName": "platform-routes"},
            },
            {"name": "template", "configMap": {"name": "platform-proxy-config"}},
        ]
        path.write_text(
            yaml.safe_dump_all(
                [
                    # platform-routes is the declared registration import volume.
                    {
                        "kind": "ConfigMap",
                        "metadata": {"name": "platform-proxy-config"},
                        "data": {"template": "public template"},
                    },
                    {
                        "kind": "ConfigMap",
                        "metadata": {"name": "platform-settings"},
                        "data": {"PORT": "8443"},
                    },
                    pod,
                ]
            )
        )
        deploy.install()
        (common.STATE / "installed/identity").unlink()
        sibling = (common.STATE / "app1/config.yaml").read_bytes()
        self.process.reset_mock()
        self.process.return_value = subprocess.CompletedProcess([], 0)
        deploy.uninstall("platform", delete_data=True)
        removals = [
            call[0][0]
            for call in self.process.call_args_list
            if call[0][0][:3] == ["podman", "volume", "rm"]
        ]
        self.assertEqual(
            removals,
            [
                ["podman", "volume", "rm", "platform-proxy-config"],
                ["podman", "volume", "rm", "platform-routes"],
            ],
        )
        self.assertEqual((common.STATE / "app1/config.yaml").read_bytes(), sibling)
        self.assertFalse((common.STATE / "platform").exists())
        self.assertTrue((common.QUADLET_DIR / "myproduct.network").exists())

    def test_invalid_mounted_config_map_refuses_before_uninstall_side_effects(self):
        deploy.install()
        output = catalog.component_paths("app1")[2]
        documents = list(yaml.safe_load_all(output.read_text()))
        pod = next(doc for doc in documents if doc.get("kind") == "Pod")
        for source in (None, {"name": []}, {"name": "app2-private"}):
            with self.subTest(source=source):
                pod["spec"]["volumes"] = [{"name": "invalid", "configMap": source}]
                output.write_text(yaml.safe_dump_all(documents))
                before = self.snapshot()
                self.process.reset_mock()
                with self.assertRaisesRegex(
                    common.DeployError, "Invalid mounted ConfigMap"
                ):
                    deploy.uninstall("app1", delete_data=True)
                self.process.assert_not_called()
                self.assertEqual(self.snapshot(), before)

    def test_invalid_component_arguments_refuse_before_any_operation(self):
        """Malformed IDs are usage errors; another bundle's component is refused."""
        for arguments, status in (
            (["init-config", "unknown"], 1),
            (["uninstall", "unknown", "--delete-data"], 1),
            (["init-config", "my_identity"], 2),
            (["uninstall", "app1", "app2"], 2),
            (["uninstall", "--delete-data", "--delete-data"], 2),
        ):
            command_line = mock.patch.object(cli.sys, "argv", ["deploy.sh"] + arguments)
            with self.subTest(arguments=arguments):
                with command_line:
                    before = self.snapshot()
                    self.process.reset_mock()
                    self.assertEqual(cli.main(), status)
                    self.process.assert_not_called()
                    self.assertEqual(self.snapshot(), before)
        self.assertIn("Usage:", self.stdout.getvalue())
        self.assertIn("not included in this bundle", self.stderr.getvalue())
        self.assertIn("can only uninstall its own component", self.stderr.getvalue())
