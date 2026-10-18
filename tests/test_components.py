"""Test component namespace and rootless isolation without Podman or systemd."""

import contextlib
import io
import json
import shutil
import subprocess
from pathlib import Path
from unittest import mock

import yaml
from catalog_fixture import (
    DEMO,
    DEMO_COMPONENTS,
    mark_installed,
    write_descriptor,
    write_secret_fixtures,
)
from test_deploy import DeployFixture, document

from deployment import catalog, cli, common, deploy, registrations
from deployment import render as rendering


class ComponentFixture(DeployFixture):
    """Exercise independent component services with temporary persistent state."""

    def setUp(self):
        """Create a minimal app1 release and two persistent configs."""
        super().setUp()
        self.write("VERSION", "1.2.3\n")
        self.write("PLATFORM_VERSION", "1.0.0\n")
        self.write("IDENTITY_VERSION", "1.0.0\n")
        self.write(
            "quadlet/template.kube",
            "[Kube]\nYaml={name}.yaml\nNetwork={product}.network\n",
        )
        self.write("quadlet/template.network", "[Network]\nNetworkName={product}\n")
        self.write("images/images.tar")
        for component in ("platform", "identity", "app1"):
            self.write(
                "home/" + component + "/config.yaml",
                "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\n",
            )
            self.component_manifest(component)

        self.select("platform")
        deploy.install()
        self.select("identity")
        deploy.install()
        self.select("app1")
        self.process.reset_mock()

    def select(self, component, **changes):
        """Unpack the demo component's compiled descriptor as this release's bundle.yaml."""
        return write_descriptor(self.root, component, **changes)

    def mark_installed(self, component, version):
        """Record a completed install of a component this test does not install."""
        mark_installed(self.root, common.HOME, component, version)
        return common.HOME / "installed" / component

    def known(self):
        """Installed metadata plus the selected bundle, as install_components builds it."""
        known = catalog.load_installed_metadata(common.HOME)
        descriptor = deploy.bundle_descriptor()
        known[descriptor["name"]] = descriptor
        return known

    def component_manifest(self, component, name=None):
        """Write a prefixed Pod with one prepared image; owners mount their imports."""
        spec = {
            "containers": [
                {
                    "name": "app",
                    "image": "localhost/" + component + ":1",
                    "imagePullPolicy": "Never",
                }
            ]
        }
        if component in ("app1", "app2"):
            # Matches the demo client.yaml, which names APP_ID and BASE_PATH.
            spec["containers"][0]["env"] = [
                {"name": "APP_ID", "value": component},
                {"name": "BASE_PATH", "value": "/" + component},
            ]
        accepts = DEMO.get(component, {}).get("accepts", {})
        if accepts:
            spec["volumes"] = [
                {"name": role, "persistentVolumeClaim": {"claimName": volume}}
                for role, volume in sorted(accepts.items())
            ]
        return self.write(
            "components/" + component + "/manifests/10-pod.yaml",
            yaml.safe_dump(document("Pod", name or component + "-worker", spec=spec)),
        )

    def imports_fixture(self):
        """Reinstall both owners in a newer version; they import current registrations."""
        for component in ("platform", "identity"):
            self.write(DEMO[component]["version_file"], "1.1.0\n")
            self.select(component)
            deploy.install()
        self.select("app1")

    def registration_fixture(self):
        """Create matching origins, a public client descriptor and a synthetic PEM."""
        for component in ("platform", "app1"):
            self.write(
                "home/" + component + "/config.yaml",
                "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\n",
            )
        source = Path(__file__).resolve().parent.parent / "components/app1"
        for name in ("route.conf", "client.yaml"):
            self.write("components/app1/" + name, (source / name).read_bytes())
        self.select("app1")
        self.write(
            "home/app1/credentials/todo/todo-client.crt",
            "-----BEGIN CERTIFICATE-----\nY2VydA==\n-----END CERTIFICATE-----\n",
        )
        work = self.root / "registration-stage"
        work.mkdir()
        return work


class ComponentTests(ComponentFixture):
    """Exercise independent component services with temporary persistent state."""

    def test_prefix_guard_rejects_each_resource_kind(self):
        """Reject unprefixed names while allowing each component's own objects."""
        for kind in ("Pod", "Secret", "PersistentVolumeClaim", "ConfigMap"):
            rendering.check_component_names(
                [document(kind, "app1-data")], "app1", "fixture.yaml"
            )
            failure = self.assertRaisesRegex(common.DeployError, "fixture.yaml.*app1-")
            with self.subTest(kind=kind), failure:
                rendering.check_component_names(
                    [document(kind, "app2-data")], "app1", "fixture.yaml"
                )

    def test_bad_prefix_fails_before_secret_generation_and_commands(self):
        """Perform namespace preflight before generating even a missing private file."""
        self.write(
            "home/platform/config.yaml",
            "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\nSECRET_FILES:\n  platform-generated:\n  - path: generated\n    generate:\n    - token\n",
        )
        self.write("PLATFORM_VERSION", "1.1.0\n")
        self.select("platform")
        self.component_manifest("platform", "wrong-pod")
        with self.assertRaisesRegex(common.DeployError, "10-pod.yaml.*platform-"):
            deploy.install()
        self.assertFalse((common.HOME / "platform/generated/token").exists())
        self.process.assert_not_called()

    def test_app_prefix_error_prevents_platform_secret_generation(self):
        """Preflight every component config before rendering any component secrets."""
        self.write(
            "home/platform/config.yaml",
            "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\nSECRET_FILES:\n  platform-generated:\n  - path: generated\n    generate:\n    - token\n",
        )
        self.write(
            "home/app1/config.yaml",
            "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\nSECRET_FILES:\n  other-token:\n  - path: missing\n",
        )
        with self.assertRaisesRegex(common.DeployError, "config.yaml.*app1-"):
            deploy.install()
        self.assertFalse((common.HOME / "platform/generated/token").exists())
        self.process.assert_not_called()

    def test_config_group_names_are_checked_before_generated_files(self):
        """Reject an unprefixed config Secret without generating private material."""
        self.write(
            "home/platform/config.yaml",
            "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\nSECRET_FILES:\n  other-token:\n  - path: generated\n    generate:\n    - token\n",
        )
        self.select("platform")
        with self.assertRaisesRegex(common.DeployError, "config.yaml.*platform-"):
            deploy.install()
        self.assertFalse((common.HOME / "platform/generated/token").exists())

    def test_install_writes_only_selected_component_services_and_state(self):
        """Keep app2 state and units unchanged while installing platform and app1."""
        siblings = [
            self.write("home/app2/config.yaml", "private fixture"),
            self.mark_installed("app2", "9.0.0"),
            self.write("systemd/myproduct-app2.yaml", "existing yaml"),
            self.write("systemd/myproduct-app2.kube", "existing kube"),
        ]
        before = {path: path.read_bytes() for path in siblings}
        deploy.install()
        self.assertTrue(
            all(path.read_bytes() == value for path, value in before.items()),
            "Sibling component was modified",
        )
        for component in ("platform", "app1"):
            _, _, output, quadlet = catalog.component_paths(component)
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
            ["myproduct-app1.service"],
        )
        self.assertFalse(any("myproduct-app2.service" in args for args in calls))

    def test_image_failure_preserves_existing_component_yaml(self):
        """Do not replace a running component's YAML after an image validation failure."""
        old = self.write("systemd/myproduct-app1.yaml", "old yaml")
        self.process.side_effect = [None, subprocess.CalledProcessError(125, "exists")]
        with self.assertRaisesRegex(common.DeployError, "unavailable"):
            deploy.install()
        self.assertEqual(old.read_text(), "old yaml")
        self.assertFalse((common.HOME / "installed/app1").exists())

    def test_help_requires_installed_platform_before_image_commands(self):
        """Reject a help-only bundle on an empty host without any image operation."""
        self.select("help")
        (common.HOME / "installed/platform").unlink()
        self.component_manifest("help")
        self.write(
            "home/help/config.yaml",
            "PUBLIC_ORIGIN: https://example.test:8443\nHTTPS_PORT: 8443\n",
        )
        with self.assertRaisesRegex(common.DeployError, "before installing help"):
            deploy.install()
        self.process.assert_not_called()

    def test_app2_installs_after_separate_platform_on_a_fresh_host(self):
        """App2 can be the first app, but never installs or restarts platform implicitly."""
        self.select("app2")
        self.component_manifest("app2")
        self.write(
            "home/app2/config.yaml",
            "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\n",
        )
        deploy.install()
        self.assertEqual((common.HOME / "installed/platform").read_text(), "1.0.0\n")
        self.assertTrue(catalog.component_paths("platform")[2].is_file())
        calls = [call.args[0] for call in self.process.call_args_list]
        self.assertNotIn(
            ["systemctl", "--user", "restart", "myproduct-platform.service"], calls
        )

    def test_platform_version_missing_equal_newer_and_older(self):
        """Apply all four platform version decisions without touching running services."""
        descriptor = self.select("platform")
        (common.HOME / "installed/platform").unlink()
        self.assertTrue(deploy.install_needed(dict(descriptor, version="1.0.0")))
        self.write("home/installed/platform", "1.2.3\n")
        self.assertFalse(deploy.install_needed(dict(descriptor, version="1.2.3")))
        self.assertTrue(deploy.install_needed(dict(descriptor, version="1.10.0")))
        with self.assertRaisesRegex(common.DeployError, "downgrade refused"):
            deploy.install_needed(dict(descriptor, version="1.2.2"))
        # upgrade: always never compares versions.
        self.assertTrue(
            deploy.install_needed(dict(descriptor, version="1.0.0", upgrade="always"))
        )

    def test_equal_platform_is_not_rewritten_or_restarted(self):
        """Keep equal-version platform YAML, secrets and service unchanged during app install."""
        deploy.install()
        platform_yaml = catalog.component_paths("platform")[2]
        before = platform_yaml.read_bytes(), platform_yaml.stat().st_mtime_ns
        # Incoming equal-version platform content must not replace installed platform files.
        incoming = self.component_manifest("platform", "platform-release-changed")
        document = rendering.load_yaml(incoming)
        document["spec"]["hostname"] = "@@NEW_PLATFORM_SETTING@@"
        incoming.write_text(yaml.safe_dump(document))
        self.process.reset_mock()
        deploy.install()
        self.assertEqual(
            (platform_yaml.read_bytes(), platform_yaml.stat().st_mtime_ns), before
        )
        restarts = [
            call.args[0]
            for call in self.process.call_args_list
            if "restart" in call.args[0]
        ]
        self.assertEqual(
            restarts, [["systemctl", "--user", "restart", "myproduct-app1.service"]]
        )

        # Once platform is selected for upgrade, a newly required key must be added manually.
        self.write("PLATFORM_VERSION", "1.1.0\n")
        self.select("platform")
        self.write(
            "components/platform/config.defaults.yaml",
            "NEW_PLATFORM_SETTING: incoming-default\n",
        )
        self.process.reset_mock()
        with self.assertRaisesRegex(
            common.DeployError, "NEW_PLATFORM_SETTING.*platform/config.yaml"
        ):
            deploy.install()
        self.process.assert_not_called()
        self.assertEqual(
            (platform_yaml.read_bytes(), platform_yaml.stat().st_mtime_ns), before
        )

    def test_prefix_ambiguous_component_ids_are_refused_before_any_change(self):
        """An installed app1-tools and an incoming app1 would share resource names."""
        self.select("app1")
        descriptor = mark_installed(self.root, common.HOME, "app2", "1.2.3")
        descriptor["name"] = "app1-tools"
        for path, text in (
            (
                catalog.metadata_path(common.HOME, "app1-tools"),
                json.dumps(descriptor, sort_keys=True),
            ),
            (common.HOME / "installed/app1-tools", "1.2.3\n"),
        ):
            path.write_text(text, encoding="utf-8")
        before = {p: p.read_bytes() for p in common.HOME.rglob("*") if p.is_file()}
        self.process.reset_mock()
        with self.assertRaisesRegex(
            common.DeployError, "component app1-tools starts with app1-"
        ):
            deploy.install()
        self.process.assert_not_called()
        self.assertEqual(
            {p: p.read_bytes() for p in common.HOME.rglob("*") if p.is_file()}, before
        )

    def test_platform_downgrade_fails_before_any_command_or_generated_file(self):
        """Reject an older app bundle's platform before touching private or runtime state."""
        self.select("platform")
        self.write("home/installed/platform", "2.0.0\n")
        self.write(
            "home/platform/config.yaml",
            "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\nSECRET_FILES:\n  platform-generated:\n  - path: generated\n    generate:\n    - token\n",
        )
        with self.assertRaisesRegex(common.DeployError, "downgrade refused"):
            deploy.install()
        self.process.assert_not_called()
        self.assertFalse((common.HOME / "platform/generated/token").exists())

    def test_registrations_stage_public_data_without_touching_siblings(self):
        """Merge app1 into a pending route/client view while preserving live app2 files."""
        work = self.registration_fixture()
        self.mark_installed("app2", "1.2.3")
        sibling = self.write("home/routes/app2.conf", "existing app2 route")
        client = self.write("home/clients/app2/client.json", '{"Id": "app2"}')
        self.write("home/clients/app2/client.crt", "existing public certificate")
        imports, updates, _ = registrations.registration_stage(
            ["app1"], work, self.known()
        )
        self.assertFalse((common.HOME / "routes/app1.conf").exists())
        self.assertEqual(sibling.read_text(), "existing app2 route")
        self.assertEqual(client.read_text(), '{"Id": "app2"}')
        self.assertEqual(
            {path.name for path in imports["identity-clients"]},
            {"app1", "app2", "installed.json"},
        )
        registration = json.loads(updates["clients/app1/client.json"])
        self.assertEqual(
            registration["RedirectUris"],
            ["https://example.test:8443/app1/auth/callback"],
        )
        self.assertEqual(registration["Id"], "app1")
        owners = {"routes": "platform", "clients": "identity"}
        self.assertEqual(
            registrations.registration_changes(updates, owners),
            {"platform", "identity"},
        )
        registrations.write_registrations(updates)
        self.assertEqual(registrations.registration_changes(updates, owners), set())
        self.assertEqual(sibling.read_text(), "existing app2 route")
        self.assertEqual(self.mode(common.HOME / "clients/app1/client.json"), 0o600)

    def test_invalid_client_and_origin_are_rejected_before_live_writes(self):
        """Reject inconsistent public origins and client identities without modifying routes."""
        work = self.registration_fixture()
        self.write(
            "home/app1/config.yaml",
            "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://other.test:8443\n",
        )
        with self.assertRaisesRegex(common.DeployError, "PUBLIC_ORIGIN.*must match"):
            deploy.install()
        self.assertFalse((common.HOME / "routes").exists())
        self.process.assert_not_called()
        self.write(
            "home/app1/config.yaml",
            "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\n",
        )
        work = self.root / "invalid-client-stage"
        work.mkdir()
        self.write(
            "components/app1/client.yaml",
            "id: app2\nbase_path: /app1\nscopes: [openid, profile, app1]\ncertificate: credentials/todo/todo-client.crt\n",
        )
        with self.assertRaisesRegex(common.DeployError, "Invalid public client"):
            registrations.registration_stage(["app1"], work, self.known())

    def test_public_origin_accepts_https_and_redacts_invalid_values(self):
        """Keep valid hostnames while rejecting malformed origins without their contents."""
        parsed = rendering.public_origin("https://example.test:8443/", "config.yaml")
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
                common.DeployError, "PUBLIC_ORIGIN.*config.yaml"
            )
            with self.subTest(value=value), failure as caught:
                rendering.public_origin(value, "config.yaml")
            self.assertNotIn("synthetic-credential", str(caught.exception))
            self.assertIsNone(caught.exception.__cause__)

    def test_platform_origin_failure_precedes_generation_and_cli_does_not_echo_value(
        self,
    ):
        """Reject a malformed platform origin before writes and keep CLI stderr free of its value."""
        secret = "synthetic-credential"
        self.write(
            "home/platform/config.yaml",
            yaml.safe_dump(
                {
                    "HTTPS_PORT": 8443,
                    "PUBLIC_ORIGIN": "https://" + secret + "＠example.test",
                    "SECRET_FILES": {
                        "platform-token": [{"path": "generated", "generate": ["token"]}]
                    },
                }
            ),
        )
        output, errors = io.StringIO(), io.StringIO()
        arguments = mock.patch.object(cli.sys, "argv", ["deploy", "install"])
        capture = contextlib.redirect_stdout(output)
        diagnostics = contextlib.redirect_stderr(errors)
        with arguments, capture, diagnostics:
            self.assertEqual(cli.main(), 1)
        self.assertIn("PUBLIC_ORIGIN", errors.getvalue())
        self.assertIn("config.yaml", errors.getvalue())
        self.assertNotIn(secret, output.getvalue() + errors.getvalue())
        self.assertFalse((common.HOME / "platform/generated/token").exists())
        self.process.assert_not_called()

    def test_registration_origin_failure_does_not_echo_value_or_write_live_state(self):
        """Reject a malformed shared origin during client staging without exposing it."""
        work = self.registration_fixture()
        origin = "https://synthetic-credential＠example.test"
        for component in ("platform", "app1"):
            self.write(
                "home/" + component + "/config.yaml",
                yaml.safe_dump({"HTTPS_PORT": 8443, "PUBLIC_ORIGIN": origin}),
            )
        with self.assertRaisesRegex(
            common.DeployError, "PUBLIC_ORIGIN.*app1/config.yaml"
        ) as caught:
            registrations.registration_stage(["app1"], work, self.known())
        self.assertNotIn("synthetic-credential", str(caught.exception))
        self.assertFalse((common.HOME / "routes").exists())
        self.assertFalse((common.HOME / "clients").exists())

    def test_equal_platform_images_are_still_verified(self):
        """A platform bundle verifies its images while retaining equal-version output."""
        self.select("platform")
        deploy.install()
        self.process.reset_mock()
        deploy.install()
        self.assertIn(
            ["podman", "image", "exists", "localhost/platform:1"],
            [call.args[0] for call in self.process.call_args_list],
        )

    def test_component_failure_hint_names_its_scoped_service(self):
        def command(arguments, **kwargs):
            if arguments == [
                "systemctl",
                "--user",
                "restart",
                "myproduct-app1.service",
            ]:
                raise subprocess.CalledProcessError(125, arguments)

        self.process.side_effect = command
        with mock.patch.object(cli.sys, "argv", ["deploy", "install"]):
            self.assertEqual(cli.main(), 1)
        self.assertIn(
            "journalctl --user -u myproduct-app1.service", self.stderr.getvalue()
        )
        self.assertNotIn("-u myproduct.service", self.stderr.getvalue())

    def test_dev_host_helper_imports_package_and_preflights_before_writes(self):
        repo = Path(__file__).resolve().parent.parent
        shutil.rmtree(self.root / "components")
        shutil.copytree(repo / "components", self.root / "components")
        shutil.copytree(
            repo / "config",
            self.root / "config",
            ignore=shutil.ignore_patterns("dev.yaml"),
        )
        for name in ("bundles.yaml", "PLATFORM_VERSION", "IDENTITY_VERSION"):
            shutil.copy2(repo / name, self.root / name)
        helper = (
            (repo / "dev/demo-credentials.sh")
            .read_text()
            .split("<<'DEMO_HOST'\n", 1)[1]
            .split("\nDEMO_HOST", 1)[0]
        )
        self.process.return_value = subprocess.CompletedProcess([], 1)
        exec(compile(helper, "dev/demo-credentials.sh:DEMO_HOST", "exec"), {})  # noqa: S102 - repository helper under test
        self.assertIn("myproduct-proxy", self.stdout.getvalue())
        self.assertFalse((common.BUILD / "dev").exists())
        self.assertEqual(len(self.process.call_args_list), 3)
        self.assertTrue(
            all(
                call.args[0][:3] == ["podman", "volume", "exists"]
                for call in self.process.call_args_list
            )
        )

    def test_dev_prepare_uses_dev_state_instead_of_service_home(self):
        """Render all real components without reading or writing the account's prod state."""
        (self.root / "bundle.yaml").unlink()
        shutil.rmtree(self.root / "components")
        repo = Path(__file__).resolve().parent.parent
        shutil.copytree(repo / "components", self.root / "components")
        for name in ("bundles.yaml", "PLATFORM_VERSION", "IDENTITY_VERSION"):
            shutil.copy2(repo / name, self.root / name)
        shutil.copytree(
            repo / "config",
            self.root / "config",
            ignore=shutil.ignore_patterns("dev.yaml"),
        )
        self.write(
            "config/dev.yaml",
            "HTTPS_PORT: 8443\nPUBLIC_ORIGIN: https://example.test:8443\nIP_ADDRESS: 127.0.0.1\n",
        )
        for component in DEMO_COMPONENTS:
            config = rendering.merge_config(
                repo / "config/common.defaults.yaml",
                repo / "components" / component / "config.defaults.yaml",
            )
            for group in ("SECRET_FILES", "VOLUME_FILES"):
                for entries in config.get(group, {}).values():
                    for source in entries:
                        entry = source["path"]
                        if ".." not in Path(entry).parts:
                            self.write(
                                "build/dev/" + component + "/" + entry + "/dummy",
                                b"dummy",
                            )
            write_secret_fixtures(
                self.root / "build/dev" / component, config, component
            )
            if component.startswith("app"):
                self.write(
                    "build/dev/" + component + "/credentials/todo/todo-client.crt",
                    "-----BEGIN CERTIFICATE-----\nY2VydA==\n-----END CERTIFICATE-----\n",
                )
        for component, relative in (
            ("identity", "identity-db"),
            ("app1", "database"),
            ("app2", "database"),
        ):
            self.write(
                "build/dev/" + component + "/credentials/" + relative + "/password",
                b"retained-db-password\n",
            )
        before = (common.HOME / "app1/config.yaml").read_bytes()
        deploy.prepare()
        self.assertEqual((common.HOME / "app1/config.yaml").read_bytes(), before)
        self.assertTrue((common.BUILD / "dev/clients/app2/client.json").exists())
        docs = list(yaml.safe_load_all((common.BUILD / "install.yaml").read_text()))
        self.assertEqual(sum(doc["kind"] == "Pod" for doc in docs), 8)
        proxy = next(
            doc
            for doc in docs
            if doc.get("kind") == "Pod" and doc["metadata"]["name"] == "platform-proxy"
        )
        self.assertEqual(proxy["spec"]["hostname"], "example.test")
        self.process.assert_not_called()

    def test_symlinked_archive_directory_cannot_modify_a_sibling(self):
        """Reject an app1 output alias to app2 before any image or write operation."""
        sibling = common.HOME / "app2/files"
        sibling.mkdir(parents=True)
        (common.HOME / "app1/files").symlink_to(sibling, target_is_directory=True)
        with self.assertRaisesRegex(common.DeployError, "symlinked component"):
            deploy.install()
        self.assertEqual(list(sibling.iterdir()), [])
        self.process.assert_not_called()

    def test_import_indexes_exclude_removed_routes_and_clients(self):
        """Overwrite active indexes so stale files left in imported volumes are ignored."""
        work = self.registration_fixture()
        registrations.registration_stage(["app1"], work, self.known())
        self.assertIn(
            "app1/client.json",
            json.loads((work / "clients/installed.json").read_text()),
        )
        self.assertIn("location /app1/", (work / "routes/installed.conf").read_text())
        empty = self.root / "empty-stage"
        empty.mkdir()
        imports, _, _ = registrations.registration_stage([], empty, self.known())
        self.assertEqual(json.loads((empty / "clients/installed.json").read_text()), [])
        self.assertEqual((empty / "routes/installed.conf").read_text(), "")
        self.assertEqual(
            [path.name for path in imports["platform-routes"]], ["installed.conf"]
        )

    def test_uninstall_preserves_siblings_and_keeps_data_by_default(self):
        """Remove app1 routing/service only while retaining app2, help, platform and the network."""
        deploy.install()
        self.mark_installed("app2", "1.2.3")
        self.mark_installed("help", "1.2.3")
        sibling = self.write("home/app2/config.yaml", "persistent app2")
        route = self.write("home/routes/app1.conf", "app1 route")
        other = self.write("home/routes/app2.conf", "app2 route")
        self.process.reset_mock()
        deploy.uninstall()
        self.assertFalse(route.exists())
        self.assertEqual(other.read_text(), "app2 route")
        self.assertEqual(sibling.read_text(), "persistent app2")
        self.assertTrue((common.HOME / "app1/config.yaml").exists())
        self.assertTrue((common.QUADLET_DIR / "myproduct.network").exists())
        self.assertFalse((common.HOME / "installed/app1").exists())
        calls = [call.args[0] for call in self.process.call_args_list]
        self.assertNotIn(
            ["systemctl", "--user", "stop", "myproduct-platform.service"], calls
        )
        self.assertFalse(any(args[:2] == ["podman", "volume"] for args in calls))

    def test_platform_uninstall_is_blocked_by_apps_or_help(self):
        """Keep shared platform available until every dependent app and help is removed."""
        deploy.install()
        self.process.reset_mock()
        self.select("platform")
        with self.assertRaisesRegex(common.DeployError, "still required"):
            deploy.uninstall("platform")
        self.process.assert_not_called()
        (common.HOME / "installed/app1").unlink()
        self.mark_installed("help", "1.2.3")
        with self.assertRaisesRegex(common.DeployError, "help"):
            deploy.uninstall("platform")

    def test_explicit_data_deletion_only_removes_own_prefixed_volumes(self):
        """Use exact own-volume names without broad deletion or touching platform volumes."""
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
        self.assertFalse((common.HOME / "app1").exists())
        self.assertTrue((common.HOME / "platform/config.yaml").exists())

    def test_help_upgrade_restart_policy_for_unchanged_and_changed_routes(self):
        """An unchanged route retains platform; a changed route restarts only help and platform."""
        deploy.install()
        self.component_manifest("help")
        self.write(
            "home/help/config.yaml",
            "PUBLIC_ORIGIN: https://example.test:8443\nHTTPS_PORT: 8443\n",
        )
        route = self.write(
            "components/help/route.conf", "location /help/ { return 200; }\n"
        )
        self.select("help")
        deploy.install()
        self.write("VERSION", "1.2.4\n")
        self.select("help")
        self.component_manifest("help")
        platform_marker = (common.HOME / "installed/platform").read_bytes()
        app_marker = (common.HOME / "installed/app1").read_bytes()
        platform_yaml = catalog.component_paths("platform")[2].read_bytes()
        platform_config = (common.HOME / "platform/config.yaml").read_bytes()
        app_config = (common.HOME / "app1/config.yaml").read_bytes()
        for changed in (False, True):
            with self.subTest(changed=changed):
                if changed:
                    route.write_text("location /help/ { return 201; }\n")
                self.process.reset_mock()
                deploy.install()
                restarts = [
                    call.args[0][-1]
                    for call in self.process.call_args_list
                    if call.args[0][:3] == ["systemctl", "--user", "restart"]
                ]
                self.assertEqual(
                    restarts,
                    ["myproduct-help.service"]
                    + (["myproduct-platform.service"] if changed else []),
                )
                self.assertEqual(
                    (common.HOME / "installed/platform").read_bytes(), platform_marker
                )
                self.assertEqual(
                    (common.HOME / "installed/app1").read_bytes(), app_marker
                )
                self.assertEqual(
                    catalog.component_paths("platform")[2].read_bytes(), platform_yaml
                )
                self.assertEqual(
                    (common.HOME / "platform/config.yaml").read_bytes(), platform_config
                )
                self.assertEqual(
                    (common.HOME / "app1/config.yaml").read_bytes(), app_config
                )
                self.assertEqual(
                    (common.HOME / "installed/help").read_text(), "1.2.4\n"
                )

    def test_newer_platform_preserves_sibling_state_in_both_app_orders(self):
        """A newer shared platform replaces platform output while every sibling file remains intact."""
        for first, second in (("app1", "app2"), ("app2", "app1")):
            with self.subTest(first=first):
                self.component_manifest(first)
                self.component_manifest(second)
                for component in (first, second):
                    self.write(
                        "home/" + component + "/config.yaml",
                        "PUBLIC_ORIGIN: https://example.test:8443\nHTTPS_PORT: 8443\n",
                    )
                self.write("PLATFORM_VERSION", "1.0.0\n")
                self.select(first)
                if (common.HOME / "installed/platform").exists():
                    (common.HOME / "installed/platform").unlink()
                self.select("platform")
                deploy.install()
                self.select(first)
                deploy.install()
                credentials = self.write(
                    "home/" + first + "/credentials/token",
                    "sibling-credential",
                    0o600,
                )
                data = self.write(
                    "home/" + first + "/data/marker", "sibling-data", 0o600
                )
                paths = [
                    credentials,
                    data,
                    common.HOME / first / "config.yaml",
                    common.HOME / "installed" / first,
                    catalog.component_paths(first)[2],
                    catalog.component_paths(first)[3],
                ]
                before = {
                    path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths
                }
                self.write("PLATFORM_VERSION", "1.1.0\n")
                self.select(second)
                self.process.reset_mock()
                self.select("platform")
                deploy.install()
                self.select(second)
                deploy.install()
                self.assertEqual(
                    {
                        path: (path.read_bytes(), path.stat().st_mtime_ns)
                        for path in paths
                    },
                    before,
                )
                self.assertEqual(
                    (common.HOME / "installed/platform").read_text(), "1.1.0\n"
                )
                restarts = [
                    call.args[0][-1]
                    for call in self.process.call_args_list
                    if call.args[0][:3] == ["systemctl", "--user", "restart"]
                ]
                self.assertEqual(
                    restarts,
                    ["myproduct-platform.service", "myproduct-" + second + ".service"],
                )
                # Reject a subsequent older release before any operation or persistent write.
                snapshot = {
                    path: (path.read_bytes(), path.stat().st_mtime_ns)
                    for path in common.HOME.rglob("*")
                    if path.is_file()
                }
                self.write("PLATFORM_VERSION", "1.0.0\n")
                self.select("platform")
                self.process.reset_mock()
                with self.assertRaisesRegex(common.DeployError, "downgrade refused"):
                    deploy.install()
                self.process.assert_not_called()
                self.assertEqual(
                    {
                        path: (path.read_bytes(), path.stat().st_mtime_ns)
                        for path in common.HOME.rglob("*")
                        if path.is_file()
                    },
                    snapshot,
                )

    def test_existing_network_is_kept_and_a_conflict_fails(self):
        """Install the shared network idempotently and refuse another definition."""
        deploy.install()
        network = common.QUADLET_DIR / "myproduct.network"
        original = network.read_bytes()
        deploy.install()
        self.assertEqual(network.read_bytes(), original)
        network.write_text("[Network]\nNetworkName=other\n")
        self.process.reset_mock()
        with self.assertRaisesRegex(common.DeployError, "shared network differs"):
            deploy.install()
        self.process.assert_not_called()
