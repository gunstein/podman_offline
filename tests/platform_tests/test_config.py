"""Explicit config layers and authoritative production state, without host operations."""

import os
import shutil
from unittest import mock

import yaml
from deployment import common, deploy, registrations
from deployment import render as rendering

from helpers.catalog_fixture import DEMO_COMPONENTS
from helpers.config_fixture import ConfigFixture


class ConfigTests(ConfigFixture):
    """Test config lifecycle using the existing component fixture."""

    def test_top_level_precedence_and_whole_mapping_list_replacement(self):
        """Every later layer replaces a whole value, including empty maps and lists."""
        common = self.write(
            "config/common.defaults.yaml",
            "HTTPS_PORT: 8443\nCHOICE: common\nSECRET_FILES:\n  platform-one:\n  - path: one\nVOLUME_FILES:\n  platform-old:\n  - path: .\n    generate:\n    - old\n",
        )
        component = self.write(
            "components/platform/config.defaults.yaml",
            "CHOICE: component\nSECRET_FILES:\n  platform-two:\n  - path: two\n  platform-generated:\n  - path: .\n    generate:\n    - new\n",
        )
        merged = rendering.merge_config(common, component)
        self.assertEqual(merged["CHOICE"], "component")
        self.assertEqual(merged["SECRET_FILES"]["platform-two"], [{"path": "two"}])
        self.assertEqual(
            merged["SECRET_FILES"]["platform-generated"][0]["generate"], ["new"]
        )
        overrides = {"CHOICE": "override", "SECRET_FILES": {}, "VOLUME_FILES": {}}
        merged = rendering.merge_config(common, component, overrides=overrides)
        for key, value in overrides.items():
            self.assertEqual(merged[key], value)

    def test_incomplete_layers_validate_only_after_merge_and_reject_duplicates(self):
        """An override may omit the port, but no source may repeat a key."""
        self.write("config/dev.yaml", "CHOICE: local\n")
        self.assertEqual(
            rendering.component_defaults("app1", dev=True)["CHOICE"], "local"
        )
        for name in (
            "config/common.defaults.yaml",
            "components/app1/config.defaults.yaml",
            "config/dev.yaml",
        ):
            path = self.root / name
            before = path.read_bytes()
            path.write_text("CHOICE: one\nCHOICE: two\n")
            failure = self.assertRaisesRegex(yaml.YAMLError, "duplicate key 'CHOICE'")
            with self.subTest(path=name):
                with failure:
                    rendering.component_defaults("app1", dev=True)
            path.write_bytes(before)
        for invalid in (
            "not: [complete\n",
            "? [private-key-value]\n: private-source-value\n",
        ):
            self.write("config/dev.yaml", invalid)
            with self.assertRaisesRegex(
                yaml.YAMLError, "dev.yaml.*invalid YAML"
            ) as failure:
                rendering.component_defaults("app1", dev=True)
            self.assertNotIn("private-key-value", str(failure.exception))
            self.assertNotIn("private-source-value", str(failure.exception))

    def test_init_modes_references_and_no_secret_or_image_operations(self):
        """Initialize complete config and private directories, without creating input files."""
        shutil.rmtree(common.STATE / "platform")
        self.write(
            "components/platform/config.defaults.yaml",
            "SECRET_FILES:\n  platform-token:\n  - path: private\n    generate:\n    - token\n",
        )
        self.select("platform")
        deploy.init_config("platform")
        target = common.STATE / "platform/config.yaml"
        config = rendering.load_config(target)
        self.assertEqual(config["PUBLIC_ORIGIN"], "https://defaults.test:8443")
        self.assertEqual(
            config["SECRET_FILES"]["platform-token"][0]["generate"], ["token"]
        )
        self.assertEqual(self.mode(target), 0o600)
        self.assertEqual(self.mode(target.parent), 0o700)
        self.assertFalse((target.parent / "private").exists())
        self.process.assert_not_called()

    def test_init_preserves_empty_invalid_and_valid_existing_files(self):
        """Existence wins over contents; ordinary install remains responsible for validation."""
        for contents in ("", "[invalid", "HTTPS_PORT: 9000\n"):
            target = self.write("home/platform/config.yaml", contents, 0o600)
            before = target.read_bytes(), target.stat().st_mtime_ns
            self.select("platform")
            deploy.init_config("platform")
            self.assertEqual((target.read_bytes(), target.stat().st_mtime_ns), before)
        self.assertIn("retained unchanged", self.stdout.getvalue())

    def test_init_bundle_selection_and_symlink_parents(self):
        """Reject unbundled components, symlinked files and any symlink ancestor."""
        with self.assertRaisesRegex(common.DeployError, "not included"):
            deploy.init_config("help")
        target = common.STATE / "platform/config.yaml"
        target.unlink()
        target.symlink_to(self.root / "absent")
        with self.assertRaisesRegex(common.DeployError, "symlinked"):
            self.select("platform")
            deploy.init_config("platform")
        target.unlink()
        shutil.rmtree(target.parent)  # Also holds platform's registration imports.
        target.parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(common.DeployError, "symlinked"):
            self.select("platform")
            deploy.init_config("platform")
        target.parent.unlink()
        alias = self.root / "alias"
        alias.symlink_to(common.STATE, target_is_directory=True)
        self.stack.enter_context(mock.patch.object(common, "HOME", alias))
        self.stack.enter_context(mock.patch.object(common, "STATE", alias))
        self.stack.enter_context(mock.patch.dict(os.environ, {"HOME": str(alias)}))
        with self.assertRaisesRegex(common.DeployError, "symlinked"):
            self.select("platform")
            deploy.init_config("platform")

    def test_init_app_reads_but_never_copies_platform_public_settings(self):
        """init-config validates with platform's values but writes none of them."""
        self.write(
            "home/platform/config.yaml",
            "HTTPS_PORT: 9443\nPUBLIC_ORIGIN: https://installed.test:9443\nCHOICE: private-platform\n",
        )
        (common.STATE / "app1/config.yaml").unlink()
        deploy.init_config("app1")
        config = rendering.load_config(common.STATE / "app1/config.yaml")
        self.assertNotIn("PUBLIC_ORIGIN", config)
        self.assertNotIn("HTTPS_PORT", config)
        self.assertEqual(config["CHOICE"], "component")
        # Install reads them from platform's config.yaml.
        settings = deploy.install_checks()[2]
        self.assertEqual(settings["PUBLIC_ORIGIN"], "https://installed.test:9443")
        self.assertEqual(settings["HTTPS_PORT"], 9443)

    def test_invalid_existing_platform_never_falls_back_to_defaults(self):
        """A present but unusable platform config is an operator error."""
        (common.STATE / "app1/config.yaml").unlink()
        for contents in (
            "",
            "HTTPS_PORT: 8443\n",
            "PUBLIC_ORIGIN: secret-invalid\nHTTPS_PORT: 8443\n",
        ):
            self.write("home/platform/config.yaml", contents)
            with self.assertRaises(common.DeployError) as failure:
                deploy.init_config("app1")
            self.assertIn("platform/config.yaml", str(failure.exception))
            self.assertNotIn("secret-invalid", str(failure.exception))
            self.assertFalse((common.STATE / "app1/config.yaml").exists())

        self.write("home/installed/platform", "1.0.0\n")
        (common.STATE / "platform/config.yaml").unlink()
        with self.assertRaisesRegex(
            common.DeployError, "platform/config.yaml; restore the installed platform"
        ):
            deploy.init_config("app1")
        self.assertFalse((common.STATE / "app1/config.yaml").exists())

    def test_production_defaults_changes_do_not_change_effective_config(self):
        """Install never reads new defaults or rewrites either persistent file."""
        paths = [
            common.STATE / name / "config.yaml"
            for name in ("platform", "identity", "app1")
        ]
        before = {p: p.read_bytes() for p in paths}
        deploy.install()
        self.write("config/common.defaults.yaml", "not valid YAML: [\n")
        self.write("components/app1/config.defaults.yaml", "HTTPS_PORT: 1\n")
        deploy.install()
        self.assertEqual({p: p.read_bytes() for p in paths}, before)
        self.assertEqual(rendering.load_config(paths[0])["HTTPS_PORT"], 8443)

    def test_new_required_placeholder_fails_before_secrets_images_or_writes(self):
        """Report config path and key, without silently adding a new release default."""
        path = self.write(
            "components/app1/manifests/20-settings.yaml",
            "kind: ConfigMap\nmetadata: {name: app1-settings}\ndata: {value: '@@NEW_REQUIRED@@'}\n",
        )
        self.write(
            "components/app1/config.defaults.yaml", "NEW_REQUIRED: sensitive-default\n"
        )
        self.write(
            "home/platform/config.yaml",
            "PUBLIC_ORIGIN: https://example.test:8443\nHTTPS_PORT: 8443\nSECRET_FILES:\n  platform-generated:\n  - path: private\n    generate:\n    - token\n",
        )
        with self.assertRaisesRegex(
            common.DeployError, "NEW_REQUIRED.*app1/config.yaml"
        ) as failure:
            deploy.install()
        self.assertNotIn("sensitive-default", str(failure.exception))
        self.assertFalse((common.STATE / "platform/private/token").exists())
        self.assertFalse((common.STATE / "installed/app1").exists())
        self.process.assert_not_called()
        self.assertTrue(path.exists())

    def test_materialized_relative_paths_ignore_defaults_source_directory(self):
        """Secret/volume/generated paths use component state in production and dev."""
        self.write(
            "components/platform/config.defaults.yaml",
            "SECRET_FILES:\n  platform-token:\n  - path: inputs/token\n  platform-generated:\n  - path: private\n    generate:\n    - generated\nVOLUME_FILES:\n  platform-content:\n  - path: content/message\n",
        )
        self.write("components/platform/inputs/token", "wrong-source")
        self.write("components/platform/content/message", "wrong-source")
        for dev in (False, True):
            with self.subTest(dev=dev):
                base = (
                    common.BUILD / "dev/platform" if dev else common.STATE / "platform"
                )
                config = rendering.component_defaults("platform", dev=dev)
                for directory, name, contents in (
                    ("inputs", "token", "materialized-secret"),
                    ("content", "message", "materialized-content"),
                ):
                    target = base / directory / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(contents)
                rendering.generate_secrets(config, base)
                secrets = rendering.load_file_group(config, "SECRET_FILES", base)
                volumes = rendering.load_file_group(config, "VOLUME_FILES", base)
                self.assertEqual(secrets["platform-token"], [base / "inputs/token"])
                self.assertEqual(
                    volumes["platform-content"], [base / "content/message"]
                )
                self.assertEqual(
                    rendering.generated_secret_paths(config, base),
                    [base / "private/generated"],
                )
                self.assertTrue((base / "private/generated").is_file())

    def test_install_refuses_own_public_settings_without_rewriting_configs(self):
        """Only platform's config.yaml holds them; a copy is refused, not corrected."""
        for settings in (
            "PUBLIC_ORIGIN: https://other.test:8443\nHTTPS_PORT: 8443\n",
            "PUBLIC_ORIGIN: https://example.test:8443\nHTTPS_PORT: 9443\n",
        ):
            path = self.write("home/app1/config.yaml", settings)
            before = path.read_bytes()
            with self.assertRaisesRegex(
                common.DeployError, "app1/config.yaml is read from platform's config"
            ):
                deploy.install()
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse((common.STATE / "installed/app1").exists())
            self.process.assert_not_called()

    def test_help_init_needs_installed_platform_settings_without_bundling_them(self):
        """A help-only bundle validates with installed platform settings, copies none."""
        self.select("help")
        self.component_manifest("help")
        self.write("components/help/config.defaults.yaml", "{}\n")
        self.write(
            "home/platform/config.yaml",
            "PUBLIC_ORIGIN: https://installed.test:9443\nHTTPS_PORT: 9443\n",
        )
        deploy.init_config("help")
        config = rendering.load_config(common.STATE / "help/config.yaml")
        self.assertNotIn("PUBLIC_ORIGIN", config)
        self.assertNotIn("HTTPS_PORT", config)
        self.process.assert_not_called()

    def test_bundle_prepare_never_uses_legacy_root_config(self):
        """Product bundles have no dev config; legacy root config is only for standalone fixtures."""
        self.write("config.yaml", "sensitive invalid root config")
        with self.assertRaisesRegex(
            common.DeployError, "Run prepare from the source checkout"
        ):
            deploy.prepare()
        self.assertFalse((common.BUILD / "install.yaml").exists())
        self.process.assert_not_called()

    def test_dev_output_is_never_a_config_layer(self):
        """Re-render defaults/overrides while keeping private credentials and data."""
        (self.root / "bundle.yaml").unlink()
        self.write(
            "bundles.yaml",
            yaml.safe_dump(
                {
                    "product": "myproduct",
                    "components": {name: {} for name in DEMO_COMPONENTS},
                }
            ),
        )
        for name in ("app2", "help"):
            self.component_manifest(name)
            self.write("components/" + name + "/config.defaults.yaml", "{}\n")
        for component in DEMO_COMPONENTS:
            self.write(
                "components/" + component + "/config.defaults.yaml",
                yaml.safe_dump(
                    {
                        "SECRET_FILES": {
                            component + "-generated": [
                                {"path": "credentials", "generate": ["token"]}
                            ]
                        }
                    }
                ),
            )
            manifest = self.root / "components" / component / "manifests/10-pod.yaml"
            pod = yaml.safe_load(manifest.read_text())
            pod["spec"]["containers"][0]["envFrom"] = [
                {"secretRef": {"name": component + "-generated"}}
            ]
            # This catalog declares no registrations.
            pod["spec"].pop("volumes", None)
            pod["spec"]["containers"][0].pop("volumeMounts", None)
            manifest.write_text(yaml.safe_dump(pod))
        output = self.write("build/dev/app1/config.yaml", "invalid: [\n")
        private = self.write(
            "build/dev/app1/credentials/token", "existing-private", 0o600
        )
        data = self.write("build/dev/app1/data/item", "persistent-data", 0o600)
        self.write(
            "config/dev.yaml",
            "CHOICE: developer\n",
        )
        # Other components generate once; app1 reuses its existing credential.
        with mock.patch.object(
            registrations, "registration_stage", return_value=({}, {}, set())
        ):
            deploy.prepare()
        self.assertEqual(rendering.load_config(output)["CHOICE"], "developer")
        before = private.read_bytes(), private.stat().st_mtime_ns
        self.write(
            "config/dev.yaml",
            "CHOICE: changed\n",
        )
        with mock.patch.object(
            registrations, "registration_stage", return_value=({}, {}, set())
        ):
            deploy.prepare()
        self.assertEqual(rendering.load_config(output)["CHOICE"], "changed")
        self.assertEqual((private.read_bytes(), private.stat().st_mtime_ns), before)
        self.assertEqual(data.read_text(), "persistent-data")
        self.process.assert_not_called()
