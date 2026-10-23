"""Identity ownership, independent registration restarts, dependencies and scoped deletion."""

import shutil
import subprocess
from pathlib import Path

import yaml
from deployment import catalog, common, deploy

from helpers.component_fixture import ComponentFixture


class IdentityTests(ComponentFixture):
    """Use actual staged registrations, import archives and temporary installed services."""

    def snapshot(self):
        return {
            str(path.relative_to(common.STATE)): (
                path.read_bytes(),
                path.stat().st_mode,
            )
            for path in common.STATE.rglob("*")
            if path.is_file()
        }

    def restarts(self):
        return [
            call[0][0][-1]
            for call in self.process.call_args_list
            if call[0][0][:3] == ["systemctl", "--user", "restart"]
        ]

    def test_route_and_client_changes_restart_only_their_owners(self):
        self.imports_fixture()
        self.registration_fixture()
        self.write(
            "home/identity/credentials/identity-db/password",
            "retained password\n",
            0o600,
        )
        deploy.install()
        protected = {
            name: value
            for name, value in self.snapshot().items()
            if name.endswith("config.yaml")
            or name.startswith(
                (
                    "identity/credentials/",
                    "installed/identity",
                    "installed/platform",
                )
            )
        }
        route = self.root / "components/app1/route.conf"
        certificate = common.STATE / "app1/credentials/todo/todo-client.crt"
        for index, (route_changed, client_changed) in enumerate(
            ((False, False), (True, False), (False, True), (True, True))
        ):
            with self.subTest(route=route_changed, client=client_changed):
                before = self.snapshot()
                if route_changed:
                    route.write_text(
                        "location /app1/ { return " + str(201 + index) + "; }\n"
                    )
                if client_changed:
                    certificate.write_text(
                        "-----BEGIN CERTIFICATE-----\n"
                        + ("YW5vdGhlcg==" if index == 2 else "Y2VydA==")
                        + "\n-----END CERTIFICATE-----\n"
                    )
                self.process.reset_mock()
                deploy.install()
                self.assertEqual(
                    self.restarts(),
                    ["myproduct-app1.service"]
                    + (["myproduct-identity.service"] if client_changed else [])
                    + (["myproduct-platform.service"] if route_changed else []),
                )
                after = self.snapshot()
                self.assertEqual({name: after[name] for name in protected}, protected)
                for owner, group, changed in (
                    ("platform", "platform-routes", route_changed),
                    ("identity", "identity-clients", client_changed),
                ):
                    name = owner + "/files/" + group + ".tar"
                    self.assertEqual(before[name] != after[name], changed)

    def test_help_works_without_identity_and_has_no_identity_side_effects(self):
        (common.STATE / "installed/identity").unlink()
        shutil.rmtree(common.STATE / "identity")
        for path in catalog.component_paths("identity")[2:]:
            path.unlink()
        self.component_manifest("help")
        self.write(
            "home/help/config.yaml",
            "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\n",
        )
        self.write("components/help/route.conf", "location /help/ { return 200; }\n")
        self.select("help")
        self.process.reset_mock()
        deploy.install()
        self.assertEqual(
            self.restarts(), ["myproduct-help.service", "myproduct-platform.service"]
        )
        self.assertFalse((common.STATE / "identity").exists())
        self.assertFalse((common.STATE / "installed/identity").exists())

    def test_missing_or_incompatible_identity_refuses_app_before_any_mutation(self):
        for version in (None, "0.9.0", "2.0.0"):
            with self.subTest(version=version):
                marker = common.STATE / "installed/identity"
                if marker.exists():
                    marker.unlink()
                if version:
                    self.write("home/installed/identity", version + "\n")
                before = self.snapshot()
                self.process.reset_mock()
                with self.assertRaisesRegex(common.DeployError, "[Ii]dentity"):
                    deploy.install()
                self.process.assert_not_called()
                self.assertEqual(self.snapshot(), before)

    def test_identity_upgrade_satisfies_installed_app_ranges_and_preserves_siblings(
        self,
    ):
        deploy.install()
        self.write("components/identity/VERSION", "2.0.0\n")
        self.select("identity")
        before = self.snapshot()
        self.process.reset_mock()
        with self.assertRaisesRegex(common.DeployError, "dependency for app1"):
            deploy.install()
        self.process.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        self.write("components/identity/VERSION", "1.1.0\n")
        self.select("identity")
        deploy.install()
        self.assertEqual(self.restarts(), ["myproduct-identity.service"])
        after = self.snapshot()
        for name, value in before.items():
            if name.startswith(
                ("platform/", "app1/", "installed/platform", "installed/app1")
            ):
                self.assertEqual(after[name], value)
        self.process.reset_mock()
        deploy.install()
        self.assertEqual(self.restarts(), [])
        self.write("components/identity/VERSION", "1.0.0\n")
        self.select("identity")
        self.process.reset_mock()
        with self.assertRaisesRegex(common.DeployError, "Identity downgrade refused"):
            deploy.install()
        self.process.assert_not_called()

    def test_uninstall_dependency_rules_and_help_does_not_block_identity(self):
        self.imports_fixture()
        repo = Path(__file__).resolve().parents[1] / "fixtures/catalog"
        self.write(
            "components/identity/route.conf",
            (repo / "components/identity/route.conf").read_text(),
        )
        self.write("components/identity/VERSION", "1.2.0\n")
        self.select("identity")
        deploy.install()
        self.select("app1")
        self.registration_fixture()
        deploy.install()
        self.select("identity")
        self.process.reset_mock()
        with self.assertRaisesRegex(common.DeployError, "still required by: app1"):
            deploy.uninstall()
        self.process.assert_not_called()
        self.select("app1")
        self.process.reset_mock()
        deploy.uninstall()
        self.assertEqual(
            self.restarts(),
            ["myproduct-identity.service", "myproduct-platform.service"],
        )
        self.assertFalse((common.STATE / "clients/app1").exists())
        self.assertFalse((common.STATE / "routes/app1.conf").exists())
        self.assertIn("identity", (common.STATE / "routes/identity.conf").read_text())
        self.mark_installed("help", "1.2.3")
        self.select("identity")
        before = (common.STATE / "identity/config.yaml").read_bytes()
        self.process.reset_mock()
        deploy.uninstall()
        self.assertEqual(self.restarts(), ["myproduct-platform.service"])
        self.assertEqual((common.STATE / "identity/config.yaml").read_bytes(), before)
        self.assertFalse((common.STATE / "routes/identity.conf").exists())
        self.assertTrue((common.STATE / "installed/help").exists())
        self.assertTrue((common.STATE / "installed/platform").exists())

    def test_identity_delete_data_removes_only_its_declared_volumes_and_state(self):
        self.select("identity")
        output = catalog.component_paths("identity")[2]
        volumes = ("identity-data", "identity-protection", "identity-signing")
        output.write_text(
            yaml.safe_dump_all(
                [
                    {
                        "kind": "Secret"
                        if name.endswith("signing")
                        else "PersistentVolumeClaim",
                        "metadata": {"name": name},
                    }
                    for name in volumes
                ]
            )
        )
        self.write("home/PKI/private/ca.key", "retained CA")
        before = self.snapshot()
        self.process.reset_mock()
        self.process.return_value = subprocess.CompletedProcess([], 0)
        deploy.uninstall(delete_data=True)
        removed = [
            call[0][0][-1]
            for call in self.process.call_args_list
            if call[0][0][:3] == ["podman", "volume", "rm"]
        ]
        self.assertEqual(removed, list(volumes))
        self.assertFalse((common.STATE / "identity").exists())
        after = self.snapshot()
        for name, value in before.items():
            if name.startswith(("platform/", "app1/", "PKI/")) or name.endswith(
                "myproduct.network"
            ):
                self.assertEqual(after[name], value)
