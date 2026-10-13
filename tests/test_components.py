"""Test component namespace and rootless isolation without Podman or systemd."""

import subprocess

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
            ["myproduct-core.service", "myproduct-app1.service"],
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
