"""Identity ownership, independent registration restarts, dependencies and retained-state refusal."""

import shutil
import subprocess
from pathlib import Path
from unittest import mock

import yaml
from test_components import ComponentFixture

import deploy

LEGACY_VOLUME_EXISTS = deploy.legacy_volume_exists


class IdentityTests(ComponentFixture):
    """Use actual staged registrations, import archives and temporary installed services."""

    def snapshot(self):
        return {
            str(path.relative_to(deploy.HOME)): (path.read_bytes(), path.stat().st_mode)
            for path in deploy.HOME.rglob("*")
            if path.is_file()
        }

    def imports_fixture(self):
        for component, group, relative in (
            ("platform", "platform-routes", "../routes"),
            ("identity", "identity-clients", "../clients"),
        ):
            config = deploy.load_config(deploy.HOME / component / "config.yaml")
            config["VOLUME_FILES"] = {group: [relative]}
            self.write("home/" + component + "/config.yaml", yaml.safe_dump(config))
            path = self.root / "components" / component / "manifests/10-pod.yaml"
            pod = yaml.safe_load(path.read_text())
            pod["spec"]["volumes"] = [
                {"name": "imports", "persistentVolumeClaim": {"claimName": group}}
            ]
            path.write_text(yaml.safe_dump(pod))
            self.write(deploy.VERSION_FILES[component], "1.1.0\n")
            self.select(component)
            deploy.install()
        self.select("app1")

    def restarts(self):
        return [
            call.args[0][-1]
            for call in self.process.call_args_list
            if call.args[0][:3] == ["systemctl", "--user", "restart"]
        ]

    def test_route_and_client_changes_restart_only_their_owners(self):
        self.imports_fixture()
        self.registration_fixture()
        self.write(
            "home/identity/generated-certificates/identity-db/password",
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
                    "identity/generated-certificates/",
                    "installed/identity",
                    "installed/platform",
                )
            )
        }
        route = self.root / "components/app1/route.conf"
        certificate = deploy.HOME / "app1/generated-certificates/todo/todo-client.crt"
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
        (deploy.HOME / "installed/identity").unlink()
        shutil.rmtree(deploy.HOME / "identity")
        for path in deploy.component_paths("identity")[2:]:
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
        self.assertFalse((deploy.HOME / "identity").exists())
        self.assertFalse((deploy.HOME / "installed/identity").exists())

    def test_missing_or_incompatible_identity_refuses_app_before_any_mutation(self):
        for version in (None, "0.9.0", "2.0.0"):
            with self.subTest(version=version):
                marker = deploy.HOME / "installed/identity"
                if marker.exists():
                    marker.unlink()
                if version:
                    self.write("home/installed/identity", version + "\n")
                before = self.snapshot()
                self.process.reset_mock()
                with self.assertRaisesRegex(deploy.DeployError, "[Ii]dentity"):
                    deploy.install()
                self.process.assert_not_called()
                self.assertEqual(self.snapshot(), before)

    def test_identity_upgrade_satisfies_installed_app_ranges_and_preserves_siblings(
        self,
    ):
        deploy.install()
        self.select("identity")
        self.write("IDENTITY_VERSION", "2.0.0\n")
        before = self.snapshot()
        self.process.reset_mock()
        with self.assertRaisesRegex(deploy.DeployError, "dependency for app1"):
            deploy.install()
        self.process.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        self.write("IDENTITY_VERSION", "1.1.0\n")
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
        self.write("IDENTITY_VERSION", "1.0.0\n")
        self.process.reset_mock()
        with self.assertRaisesRegex(deploy.DeployError, "Identity downgrade refused"):
            deploy.install()
        self.process.assert_not_called()

    def test_uninstall_dependency_rules_and_help_does_not_block_identity(self):
        self.imports_fixture()
        repo = Path(__file__).resolve().parent.parent
        self.write(
            "components/identity/route.conf",
            (repo / "components/identity/route.conf").read_text(),
        )
        self.write("IDENTITY_VERSION", "1.2.0\n")
        self.select("identity")
        deploy.install()
        self.select("app1")
        self.registration_fixture()
        deploy.install()
        self.select("identity")
        self.process.reset_mock()
        with self.assertRaisesRegex(deploy.DeployError, "still required by: app1"):
            deploy.uninstall()
        self.process.assert_not_called()
        self.select("app1")
        self.process.reset_mock()
        deploy.uninstall()
        self.assertEqual(
            self.restarts(),
            ["myproduct-identity.service", "myproduct-platform.service"],
        )
        self.assertFalse((deploy.HOME / "clients/app1").exists())
        self.assertFalse((deploy.HOME / "routes/app1.conf").exists())
        self.assertIn("identity", (deploy.HOME / "routes/identity.conf").read_text())
        self.write("home/installed/help", "1.2.3\n")
        self.select("identity")
        before = (deploy.HOME / "identity/config.yaml").read_bytes()
        self.process.reset_mock()
        deploy.uninstall()
        self.assertEqual(self.restarts(), ["myproduct-platform.service"])
        self.assertEqual((deploy.HOME / "identity/config.yaml").read_bytes(), before)
        self.assertFalse((deploy.HOME / "routes/identity.conf").exists())
        self.assertTrue((deploy.HOME / "installed/help").exists())
        self.assertTrue((deploy.HOME / "installed/platform").exists())

    def test_identity_delete_data_removes_only_its_declared_volumes_and_state(self):
        self.select("identity")
        output = deploy.component_paths("identity")[2]
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
            call.args[0][-1]
            for call in self.process.call_args_list
            if call.args[0][:3] == ["podman", "volume", "rm"]
        ]
        self.assertEqual(removed, list(volumes))
        self.assertFalse((deploy.HOME / "identity").exists())
        after = self.snapshot()
        for name, value in before.items():
            if name.startswith(("platform/", "app1/", "PKI/")) or name.endswith(
                "myproduct.network"
            ):
                self.assertEqual(after[name], value)

    def test_combined_credentials_config_marker_and_unit_are_refused_unchanged(self):
        self.select("identity")
        paths = (
            "platform/generated-certificates/identity/key",
            "platform/generated-certificates/identity-db/password",
            "platform/generated-certificates/users/alice-password",
            "platform/generated-certificates/app/token",
            "platform/files/platform-clients.tar",
        )
        for name in paths:
            path = self.write("home/" + name, "retained old private state")
            before = self.snapshot()
            self.process.reset_mock()
            with self.assertRaisesRegex(
                deploy.DeployError, "Combined platform/Identity.*migration"
            ):
                deploy.install()
            self.process.assert_not_called()
            self.assertEqual(self.snapshot(), before)
            path.unlink()
            if "generated-certificates/" in name:
                path.parent.rmdir()
        for name, text in (
            ("platform/config.yaml", "DB_HOST: platform-identity-postgres\n"),
            ("installed/platform", "0.3.0\n"),
            (
                ".config/containers/systemd/myproduct-platform.yaml",
                "kind: Pod\nmetadata: {name: platform-identity}\n",
            ),
        ):
            path = deploy.HOME / name
            original = path.read_bytes()
            path.write_text(text)
            before = self.snapshot()
            with self.assertRaisesRegex(
                deploy.DeployError, "Combined platform/Identity.*migration"
            ):
                deploy.install()
            self.assertEqual(self.snapshot(), before)
            path.write_bytes(original)

    def test_retained_combined_volumes_without_marker_refuse_all_component_operations(
        self,
    ):
        self.select("identity")
        for volume in (
            "platform-identity-data",
            "platform-identity-protection",
            "platform-clients",
        ):
            for operation in (
                lambda: deploy.init_config("identity"),
                deploy.install,
                deploy.uninstall,
            ):
                with self.subTest(volume=volume, operation=operation):
                    self.process.side_effect = lambda args, volume=volume, **kwargs: (
                        subprocess.CompletedProcess(
                            args, 0 if args[-1] == volume else 1
                        )
                    )
                    before = self.snapshot()
                    volume_check = mock.patch.object(
                        deploy, "legacy_volume_exists", side_effect=LEGACY_VOLUME_EXISTS
                    )
                    refusal = self.assertRaisesRegex(
                        deploy.DeployError, "combined platform volume.*migration"
                    )
                    with volume_check, refusal:
                        operation()
                    self.assertEqual(self.snapshot(), before)
                    self.assertTrue(
                        all(
                            call.args[0][:3] == ["podman", "volume", "exists"]
                            for call in self.process.call_args_list
                        )
                    )
                    self.process.reset_mock()

    def test_identity_owns_database_signing_and_clients_and_proxy_has_no_fixed_identity(
        self,
    ):
        repo = Path(__file__).resolve().parent.parent
        platform = deploy.merge_config(
            repo / "config/common.defaults.yaml",
            repo / "components/platform/config.defaults.yaml",
        )
        identity = deploy.merge_config(
            repo / "config/common.defaults.yaml",
            repo / "components/identity/config.defaults.yaml",
        )
        self.assertFalse(any(name.startswith("DB_") for name in platform))
        self.assertNotIn("GENERATED_SECRETS", platform)
        self.assertEqual(set(platform["VOLUME_FILES"]), {"platform-routes"})
        self.assertEqual(set(identity["VOLUME_FILES"]), {"identity-clients"})
        self.assertEqual(identity["DB_HOST"], "identity-postgres")
        self.assertEqual(identity["DB_USER"], "identity")
        self.assertNotIn("/identity/", (repo / "apps/proxy/default.conf").read_text())
        route = (repo / "components/identity/route.conf").read_text()
        self.assertIn("location /identity/", route)
        self.assertIn("set $identity_upstream identity-server:8080", route)
        self.assertIn("proxy_pass http://$identity_upstream", route)
