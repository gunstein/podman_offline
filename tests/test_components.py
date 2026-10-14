"""Test component namespace and rootless isolation without Podman or systemd."""

import contextlib
import io
import json
import shutil
import subprocess
from pathlib import Path
from unittest import mock

import yaml
from test_deploy import DeployFixture, document

import deploy


class ComponentTests(DeployFixture):
    """Exercise independent component services with temporary persistent state."""

    def setUp(self):
        """Create a minimal app1 release and two persistent configs."""
        super().setUp()
        self.write("bundle.yaml", "name: app1\ncomponents: [core, app1]\n")
        self.write("VERSION", "1.2.3\n")
        self.write("CORE_VERSION", "1.0.0\n")
        self.write(
            "quadlet/myproduct.kube",
            "[Kube]\nYaml=myproduct.yaml\nNetwork=myproduct.network\n",
        )
        self.write("quadlet/myproduct.network", "[Network]\nNetworkName=myproduct\n")
        self.write("images/images.tar")
        for component in ("core", "app1"):
            self.write("home/" + component + "/config.yaml", "HTTPS_PORT: 8443\n")
            self.component_manifest(component)

    def component_manifest(self, component, name=None):
        """Write a prefixed Pod with one prepared image."""
        return self.write(
            "components/" + component + "/manifests/10-pod.yaml",
            yaml.safe_dump(
                document(
                    "Pod",
                    name or component + "-worker",
                    spec={
                        "containers": [
                            {
                                "name": "app",
                                "image": "localhost/" + component + ":1",
                                "imagePullPolicy": "Never",
                            }
                        ]
                    },
                )
            ),
        )

    def test_prefix_guard_rejects_each_resource_kind(self):
        """Reject unprefixed names while allowing each component's own objects."""
        for kind in ("Pod", "Secret", "PersistentVolumeClaim", "ConfigMap"):
            deploy.check_component_names(
                [document(kind, "app1-data")], "app1", "fixture.yaml"
            )
            failure = self.assertRaisesRegex(deploy.DeployError, "fixture.yaml.*app1-")
            with self.subTest(kind=kind), failure:
                deploy.check_component_names(
                    [document(kind, "app2-data")], "app1", "fixture.yaml"
                )

    def test_bad_prefix_fails_before_secret_generation_and_commands(self):
        """Perform namespace preflight before generating even a missing private file."""
        self.write(
            "home/core/config.yaml",
            "HTTPS_PORT: 8443\nGENERATED_SECRETS: [generated/token]\n",
        )
        self.component_manifest("core", "wrong-pod")
        with self.assertRaisesRegex(deploy.DeployError, "10-pod.yaml.*core-"):
            deploy.install()
        self.assertFalse((deploy.HOME / "core/generated/token").exists())
        self.process.assert_not_called()

    def test_app_prefix_error_prevents_core_secret_generation(self):
        """Preflight every component config before rendering any component secrets."""
        self.write(
            "home/core/config.yaml",
            "HTTPS_PORT: 8443\nGENERATED_SECRETS: [generated/token]\n",
        )
        self.write(
            "home/app1/config.yaml",
            "HTTPS_PORT: 8443\nSECRET_FILES: {other-token: [missing]}\n",
        )
        with self.assertRaisesRegex(deploy.DeployError, "config.yaml.*app1-"):
            deploy.install()
        self.assertFalse((deploy.HOME / "core/generated/token").exists())
        self.process.assert_not_called()

    def test_config_group_names_are_checked_before_generated_files(self):
        """Reject an unprefixed config Secret without generating private material."""
        self.write(
            "home/core/config.yaml",
            "HTTPS_PORT: 8443\nGENERATED_SECRETS: [generated/token]\nSECRET_FILES: {other-token: [generated/token]}\n",
        )
        with self.assertRaisesRegex(deploy.DeployError, "config.yaml.*core-"):
            deploy.install()
        self.assertFalse((deploy.HOME / "core/generated/token").exists())

    def test_install_writes_only_selected_component_services_and_state(self):
        """Keep app2 state and units unchanged while installing core and app1."""
        siblings = [
            self.write("home/app2/config.yaml", "private fixture"),
            self.write("home/installed/app2", "9.0.0\n"),
            self.write("systemd/myproduct-app2.yaml", "existing yaml"),
            self.write("systemd/myproduct-app2.kube", "existing kube"),
        ]
        before = {path: path.read_bytes() for path in siblings}
        deploy.install()
        self.assertTrue(
            all(path.read_bytes() == value for path, value in before.items()),
            "Sibling component was modified",
        )
        for component in ("core", "app1"):
            _, _, output, quadlet = deploy.component_paths(component)
            self.assertEqual(self.mode(output), 0o600)
            self.assertEqual(self.mode(quadlet), 0o644)
            self.assertIn("Yaml=" + output.name, quadlet.read_text())
        calls = [call.args[0] for call in self.process.call_args_list]
        self.assertEqual(
            [
                args[-1]
                for args in calls
                if args[:3] == ["systemctl", "--user", "restart"]
            ],
            ["myproduct-app1.service", "myproduct-core.service"],
        )
        self.assertFalse(any("myproduct-app2.service" in args for args in calls))

    def test_image_failure_preserves_existing_component_yaml(self):
        """Do not replace a running component's YAML after an image validation failure."""
        old = self.write("systemd/myproduct-app1.yaml", "old yaml")
        self.process.side_effect = [None, subprocess.CalledProcessError(125, "exists")]
        with self.assertRaisesRegex(deploy.DeployError, "unavailable"):
            deploy.install()
        self.assertEqual(old.read_text(), "old yaml")
        self.assertFalse((deploy.HOME / "installed/app1").exists())

    def test_help_requires_installed_core_before_image_commands(self):
        """Reject a help-only bundle on an empty host without any image operation."""
        self.write("bundle.yaml", "name: help\ncomponents: [help]\n")
        with self.assertRaisesRegex(deploy.DeployError, "before installing help"):
            deploy.install()
        self.process.assert_not_called()

    def test_core_version_missing_equal_newer_and_older(self):
        """Apply all four core version decisions without touching running services."""
        self.assertTrue(deploy.core_upgrade_needed("1.0.0"))
        self.write("home/installed/core", "1.2.3\n")
        self.assertFalse(deploy.core_upgrade_needed("1.2.3"))
        self.assertTrue(deploy.core_upgrade_needed("1.10.0"))
        with self.assertRaisesRegex(deploy.DeployError, "downgrade refused"):
            deploy.core_upgrade_needed("1.2.2")

    def test_equal_core_is_not_rewritten_or_restarted(self):
        """Keep equal-version core YAML, secrets and service unchanged during app install."""
        deploy.install()
        core_yaml = deploy.component_paths("core")[2]
        before = core_yaml.read_bytes(), core_yaml.stat().st_mtime_ns
        self.process.reset_mock()
        deploy.install()
        self.assertEqual((core_yaml.read_bytes(), core_yaml.stat().st_mtime_ns), before)
        restarts = [
            call.args[0]
            for call in self.process.call_args_list
            if "restart" in call.args[0]
        ]
        self.assertEqual(
            restarts, [["systemctl", "--user", "restart", "myproduct-app1.service"]]
        )

    def test_core_downgrade_fails_before_any_command_or_generated_file(self):
        """Reject an older app bundle's core before touching private or runtime state."""
        self.write("home/installed/core", "2.0.0\n")
        self.write(
            "home/core/config.yaml",
            "HTTPS_PORT: 8443\nGENERATED_SECRETS: [generated/token]\n",
        )
        with self.assertRaisesRegex(deploy.DeployError, "downgrade refused"):
            deploy.install()
        self.process.assert_not_called()
        self.assertFalse((deploy.HOME / "core/generated/token").exists())

    def registration_fixture(self):
        """Create matching origins, a public client descriptor and a synthetic PEM."""
        for component in ("core", "app1"):
            self.write(
                "home/" + component + "/config.yaml",
                "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\n",
            )
        source = Path(__file__).resolve().parent.parent / "components/app1"
        for name in ("route.conf", "client.yaml"):
            self.write("components/app1/" + name, (source / name).read_bytes())
        self.write(
            "home/app1/generated-certificates/todo/todo-client.crt",
            "-----BEGIN CERTIFICATE-----\nY2VydA==\n-----END CERTIFICATE-----\n",
        )
        work = self.root / "registration-stage"
        work.mkdir()
        return work

    def test_registrations_stage_public_data_without_touching_siblings(self):
        """Merge app1 into a pending route/client view while preserving live app2 files."""
        work = self.registration_fixture()
        sibling = self.write("home/routes/app2.conf", "existing app2 route")
        client = self.write("home/clients/app2/client.json", "existing app2 client")
        self.write("home/clients/app2/client.crt", "existing public certificate")
        imports, updates = deploy.registration_stage(["app1"], work)
        self.assertFalse((deploy.HOME / "routes/app1.conf").exists())
        self.assertEqual(sibling.read_text(), "existing app2 route")
        self.assertEqual(client.read_text(), "existing app2 client")
        self.assertEqual(
            {path.name for path in imports["core-clients"]},
            {"app1", "app2", "installed.json"},
        )
        registration = json.loads(updates["clients/app1/client.json"])
        self.assertEqual(
            registration["RedirectUris"],
            ["https://example.test:8443/app1/auth/callback"],
        )
        self.assertEqual(registration["Id"], "app1")
        self.assertTrue(deploy.write_registrations(updates))
        self.assertFalse(deploy.write_registrations(updates))
        self.assertEqual(sibling.read_text(), "existing app2 route")
        self.assertEqual(self.mode(deploy.HOME / "clients/app1/client.json"), 0o600)

    def test_invalid_client_and_origin_are_rejected_before_live_writes(self):
        """Reject inconsistent public origins and client identities without modifying routes."""
        work = self.registration_fixture()
        self.write(
            "home/app1/config.yaml",
            "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://other.test:8443\n",
        )
        with self.assertRaisesRegex(deploy.DeployError, "must match"):
            deploy.registration_stage(["app1"], work)
        self.assertFalse((deploy.HOME / "routes").exists())
        self.write(
            "home/app1/config.yaml",
            "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\n",
        )
        work = self.root / "invalid-client-stage"
        work.mkdir()
        self.write(
            "components/app1/client.yaml",
            "id: app2\nbase_path: /app1\nscopes: [openid, profile, app1]\ncertificate: generated-certificates/todo/todo-client.crt\n",
        )
        with self.assertRaisesRegex(deploy.DeployError, "Invalid public client"):
            deploy.registration_stage(["app1"], work)

    def test_public_origin_accepts_https_and_redacts_invalid_values(self):
        """Keep valid hostnames while rejecting malformed origins without their contents."""
        parsed = deploy.public_origin("https://example.test:8443/", "config.yaml")
        self.assertEqual(parsed.hostname, "example.test")
        self.assertEqual(parsed.geturl(), "https://example.test:8443")
        values = (
            "https://synthetic-credential＠example.test",
            "https://[synthetic-credential",
            "https://user:synthetic-credential@example.test",
            "https://example.test/?synthetic-credential",
            "https://example.test/#synthetic-credential",
            "https://example.test/synthetic-credential",
            "http://synthetic-credential.example.test",
            1234,
        )
        for value in values:
            failure = self.assertRaisesRegex(
                deploy.DeployError, "PUBLIC_ORIGIN.*config.yaml"
            )
            with self.subTest(value=value), failure as caught:
                deploy.public_origin(value, "config.yaml")
            self.assertNotIn("synthetic-credential", str(caught.exception))
            self.assertIsNone(caught.exception.__cause__)

    def test_core_origin_failure_precedes_generation_and_cli_does_not_echo_value(self):
        """Reject a malformed core origin before writes and keep CLI stderr free of its value."""
        secret = "synthetic-credential"
        self.write(
            "home/core/config.yaml",
            yaml.safe_dump(
                {
                    "HTTPS_PORT": 8443,
                    "PUBLIC_ORIGIN": "https://" + secret + "＠example.test",
                    "GENERATED_SECRETS": ["generated/token"],
                }
            ),
        )
        output, errors = io.StringIO(), io.StringIO()
        arguments = mock.patch.object(deploy.sys, "argv", ["deploy", "install"])
        capture = contextlib.redirect_stdout(output)
        diagnostics = contextlib.redirect_stderr(errors)
        with arguments, capture, diagnostics:
            self.assertEqual(deploy.main(), 1)
        self.assertIn("PUBLIC_ORIGIN", errors.getvalue())
        self.assertIn("config.yaml", errors.getvalue())
        self.assertNotIn(secret, output.getvalue() + errors.getvalue())
        self.assertFalse((deploy.HOME / "core/generated/token").exists())
        self.process.assert_not_called()

    def test_registration_origin_failure_does_not_echo_value_or_write_live_state(self):
        """Reject a malformed shared origin during client staging without exposing it."""
        work = self.registration_fixture()
        origin = "https://synthetic-credential＠example.test"
        for component in ("core", "app1"):
            self.write(
                "home/" + component + "/config.yaml",
                yaml.safe_dump({"HTTPS_PORT": 8443, "PUBLIC_ORIGIN": origin}),
            )
        with self.assertRaisesRegex(
            deploy.DeployError, "PUBLIC_ORIGIN.*app1/config.yaml"
        ) as caught:
            deploy.registration_stage(["app1"], work)
        self.assertNotIn("synthetic-credential", str(caught.exception))
        self.assertFalse((deploy.HOME / "routes").exists())
        self.assertFalse((deploy.HOME / "clients").exists())

    def test_equal_core_images_are_still_verified(self):
        """Verify bundled core image names even when the equal core service is retained."""
        deploy.install()
        self.process.reset_mock()
        deploy.install()
        self.assertIn(
            ["podman", "image", "exists", "localhost/core:1"],
            [call.args[0] for call in self.process.call_args_list],
        )

    def test_dev_prepare_uses_dev_state_instead_of_service_home(self):
        """Render all real components without reading or writing the account's prod state."""
        (self.root / "bundle.yaml").unlink()
        shutil.rmtree(self.root / "components")
        repo = Path(__file__).resolve().parent.parent
        shutil.copytree(repo / "components", self.root / "components")
        self.write(
            "config.yaml",
            "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\nIP_ADDRESS: 127.0.0.1\n",
        )
        for component in ("core", "app1", "app2", "help"):
            config = deploy.load_config(
                repo / "components" / component / "config.example.yaml"
            )
            for group in ("SECRET_FILES", "VOLUME_FILES"):
                for entries in config.get(group, {}).values():
                    for entry in entries:
                        if ".." not in Path(entry).parts:
                            self.write(
                                "build/dev/" + component + "/" + entry + "/dummy",
                                b"dummy",
                            )
            if component.startswith("app"):
                self.write(
                    "build/dev/"
                    + component
                    + "/generated-certificates/todo/todo-client.crt",
                    "-----BEGIN CERTIFICATE-----\nY2VydA==\n-----END CERTIFICATE-----\n",
                )
        before = (deploy.HOME / "app1/config.yaml").read_bytes()
        deploy.prepare()
        self.assertEqual((deploy.HOME / "app1/config.yaml").read_bytes(), before)
        self.assertTrue((deploy.BUILD / "dev/clients/app2/client.json").exists())
        docs = list(yaml.safe_load_all((deploy.BUILD / "install.yaml").read_text()))
        self.assertEqual(sum(doc["kind"] == "Pod" for doc in docs), 8)
        proxy = next(
            doc
            for doc in docs
            if doc.get("kind") == "Pod" and doc["metadata"]["name"] == "core-proxy"
        )
        self.assertEqual(proxy["spec"]["hostname"], "example.test")
        self.process.assert_not_called()

    def test_symlinked_archive_directory_cannot_modify_a_sibling(self):
        """Reject an app1 output alias to app2 before any image or write operation."""
        sibling = deploy.HOME / "app2/files"
        sibling.mkdir(parents=True)
        (deploy.HOME / "app1/files").symlink_to(sibling, target_is_directory=True)
        with self.assertRaisesRegex(deploy.DeployError, "symlinked component"):
            deploy.install()
        self.assertEqual(list(sibling.iterdir()), [])
        self.process.assert_not_called()

    def test_import_indexes_exclude_removed_routes_and_clients(self):
        """Overwrite active indexes so stale files left in imported volumes are ignored."""
        work = self.registration_fixture()
        deploy.registration_stage(["app1"], work)
        self.assertIn(
            "app1/client.json",
            json.loads((work / "clients/installed.json").read_text()),
        )
        self.assertIn("location /app1/", (work / "routes/installed.conf").read_text())
        empty = self.root / "empty-stage"
        empty.mkdir()
        imports, _ = deploy.registration_stage([], empty)
        self.assertEqual(json.loads((empty / "clients/installed.json").read_text()), [])
        self.assertEqual((empty / "routes/installed.conf").read_text(), "")
        self.assertEqual(
            [path.name for path in imports["core-routes"]], ["installed.conf"]
        )

    def test_uninstall_preserves_siblings_and_keeps_data_by_default(self):
        """Remove app1 routing/service only while retaining app2, help, core and the network."""
        deploy.install()
        self.write("home/installed/app2", "1.2.3\n")
        self.write("home/installed/help", "1.2.3\n")
        sibling = self.write("home/app2/config.yaml", "persistent app2")
        route = self.write("home/routes/app1.conf", "app1 route")
        other = self.write("home/routes/app2.conf", "app2 route")
        self.process.reset_mock()
        deploy.uninstall()
        self.assertFalse(route.exists())
        self.assertEqual(other.read_text(), "app2 route")
        self.assertEqual(sibling.read_text(), "persistent app2")
        self.assertTrue((deploy.HOME / "app1/config.yaml").exists())
        self.assertTrue((deploy.QUADLET_DIR / "myproduct.network").exists())
        self.assertFalse((deploy.HOME / "installed/app1").exists())
        calls = [call.args[0] for call in self.process.call_args_list]
        self.assertNotIn(
            ["systemctl", "--user", "stop", "myproduct-core.service"], calls
        )
        self.assertFalse(any(args[:2] == ["podman", "volume"] for args in calls))

    def test_core_uninstall_is_blocked_by_apps_or_help(self):
        """Keep shared core available until every dependent app and help is removed."""
        deploy.install()
        self.process.reset_mock()
        with self.assertRaisesRegex(deploy.DeployError, "still required"):
            deploy.uninstall("core")
        self.process.assert_not_called()
        (deploy.HOME / "installed/app1").unlink()
        self.write("home/installed/help", "1.2.3\n")
        with self.assertRaisesRegex(deploy.DeployError, "help"):
            deploy.uninstall("core")

    def test_explicit_data_deletion_only_removes_own_prefixed_volumes(self):
        """Use exact own-volume names without broad deletion or touching core volumes."""
        pod = document(
            "Pod",
            "app1-worker",
            spec={
                "containers": [
                    {
                        "name": "app",
                        "image": "localhost/app1:1",
                        "imagePullPolicy": "Never",
                        "volumeMounts": [{"name": "data", "mountPath": "/data"}],
                    }
                ],
                "volumes": [
                    {
                        "name": "data",
                        "persistentVolumeClaim": {"claimName": "app1-data"},
                    }
                ],
            },
        )
        self.write(
            "components/app1/manifests/10-pod.yaml",
            yaml.safe_dump_all([document("PersistentVolumeClaim", "app1-data"), pod]),
        )
        deploy.install()
        self.process.reset_mock()
        self.process.return_value = subprocess.CompletedProcess([], 0)
        deploy.uninstall(delete_data=True)
        calls = [call.args[0] for call in self.process.call_args_list]
        self.assertIn(["podman", "volume", "rm", "app1-data"], calls)
        self.assertFalse(any("--all" in args or "--force" in args for args in calls))
        self.assertFalse((deploy.HOME / "app1").exists())
        self.assertTrue((deploy.HOME / "core/config.yaml").exists())

    def test_existing_network_is_kept_and_a_conflict_fails(self):
        """Install the shared network idempotently and refuse another definition."""
        deploy.install()
        network = deploy.QUADLET_DIR / "myproduct.network"
        original = network.read_bytes()
        deploy.install()
        self.assertEqual(network.read_bytes(), original)
        network.write_text("[Network]\nNetworkName=other\n")
        self.process.reset_mock()
        with self.assertRaisesRegex(deploy.DeployError, "shared network differs"):
            deploy.install()
        self.process.assert_not_called()
