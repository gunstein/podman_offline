"""Manifest validation runs before secret generation, output and host commands.

Backlog item 21, section 4: on every path (install, dev prepare, standalone
prepare and install) a manifest error that can be decided from declarations
must leave no generated secret, import archive, YAML or Podman call behind.
"""

import shutil
from unittest import mock

import yaml
from deployment import catalog, common, deploy
from deployment import render as rendering

from helpers.deploy_fixture import DeployFixture, document
from helpers.product_fixture import RENAMED, ProductFixture
from helpers.validation_fixture import CASES, broken_orders


class ProductValidationOrderTests(ProductFixture):
    def setUp(self):
        super().setUp()
        self.write_product(RENAMED)

    def write_orders(self, root, documents):
        (root / "components/orders/manifests/10-resources.yaml").write_text(
            yaml.safe_dump_all(documents, sort_keys=False)
        )

    def test_install_validates_before_preflight_generation_or_writes(self):
        releases = self.build_and_unpack()
        shutil.rmtree(self.source)
        self.provide_credentials(RENAMED, common.STATE)
        self.install(releases["gateway"])
        self.install(releases["login-service"])
        release = releases["orders"]
        self.use_root(release)
        deploy.init_config("orders")
        password = common.STATE / "orders/credentials/database/password"
        for case in CASES:
            with self.subTest(case=case):
                documents, message = broken_orders(case)
                self.write_orders(release, documents)
                before = self.files_under(common.STATE)
                self.process.reset_mock()
                with self.assertRaisesRegex(common.DeployError, message):
                    deploy.install()
                # Not even the database volume check: it follows validation.
                self.assertEqual(self.commands(), [])
                self.assertEqual(self.files_under(common.STATE), before)
                self.assertFalse(password.exists())

    def test_install_renders_once_and_writes_what_it_validated(self):
        releases = self.build_and_unpack()
        shutil.rmtree(self.source)
        self.provide_credentials(RENAMED, common.STATE)
        for name in ("gateway", "login-service"):
            self.install(releases[name])
        results = []
        original = rendering.materialize

        def materialize(*args, **kwargs):
            results.append(original(*args, **kwargs))
            return results[-1]

        with mock.patch.object(rendering, "materialize", side_effect=materialize):
            self.install(releases["orders"])
        # One generation and render; the installed YAML is exactly that render.
        self.assertEqual(len(results), 1)
        self.assertEqual(
            catalog.component_paths("orders")[2].read_text(), results[0][0]
        )
        self.assertTrue(
            (common.STATE / "orders/credentials/database/password").is_file()
        )

    def test_dev_prepare_validates_every_component_before_any_write(self):
        dev = common.BUILD / "dev"
        self.provide_credentials(RENAMED, dev)
        for case in CASES:
            with self.subTest(case=case):
                documents, message = broken_orders(case)
                self.write_orders(self.source, documents)
                before = self.files_under(dev)
                self.process.reset_mock()
                with self.assertRaisesRegex(common.DeployError, message):
                    deploy.prepare()
                self.assertEqual(self.commands(), [])
                self.assertEqual(self.files_under(dev), before)
                self.assertFalse((common.BUILD / "install.yaml").exists())


class RegistrationValidationOrderTests(ProductFixture):
    """Registrations are validated by staging, before any write or host command."""

    BROKEN = "id: orders\nbase_path: no-slash\nscopes: [openid]\ncertificate: x\n"

    def setUp(self):
        super().setUp()
        self.write_product(RENAMED)

    def test_install_validates_registrations_before_host_commands(self):
        releases = self.build_and_unpack()
        shutil.rmtree(self.source)
        self.provide_credentials(RENAMED, common.STATE)
        self.install(releases["gateway"])
        self.install(releases["login-service"])
        release = releases["orders"]
        self.use_root(release)
        deploy.init_config("orders")
        (release / "components/orders/client.yaml").write_text(self.BROKEN)
        before = self.files_under(common.STATE)
        self.process.reset_mock()
        with self.assertRaisesRegex(common.DeployError, "Invalid public client"):
            deploy.install()
        self.assertEqual(self.commands(), [])
        self.assertEqual(self.files_under(common.STATE), before)

    def test_dev_prepare_validates_registrations_before_any_write(self):
        dev = common.BUILD / "dev"
        self.provide_credentials(RENAMED, dev)
        deploy.prepare()
        (self.source / "components/orders/client.yaml").write_text(self.BROKEN)
        before = self.files_under(dev)
        self.process.reset_mock()
        with self.assertRaisesRegex(common.DeployError, "Invalid public client"):
            deploy.prepare()
        # Configs are not rewritten and the dev registrations are not deleted.
        self.assertEqual(self.files_under(dev), before)
        self.assertEqual(self.commands(), [])


class ImportedVolumeMessageTests(DeployFixture):
    def test_unused_imported_volume_names_bundles_yaml(self):
        """An accepts volume no manifest mounts is reported where it is declared."""
        self.manifest(
            [
                document(
                    "Pod",
                    "app",
                    spec={
                        "containers": [
                            {
                                "name": "web",
                                "image": "localhost/app:1",
                                "imagePullPolicy": "Never",
                            }
                        ]
                    },
                )
            ],
            "20-images.yaml",
        )
        with self.assertRaisesRegex(
            common.DeployError,
            "Imported volume gw-routes \\(accepts in bundles.yaml\\)",
        ):
            rendering.effective_documents(
                {},
                (common.ROOT / "config.yaml"),
                (common.ROOT / "manifests"),
                None,
                ["gw-routes"],
            )

    def test_declared_but_unmounted_imported_volume_is_refused(self):
        """Backlog 77, R3: a Pod volume for the PVC is not enough; mount it."""
        container = {
            "name": "web",
            "image": "localhost/app:1",
            "imagePullPolicy": "Never",
        }
        spec = {
            "containers": [container],
            "volumes": [
                {"name": "routes", "persistentVolumeClaim": {"claimName": "gw-routes"}}
            ],
        }
        self.manifest([document("Pod", "app", spec=spec)], "20-images.yaml")
        with self.assertRaisesRegex(
            common.DeployError,
            "receives registrations in volume gw-routes; mount it with volumeMounts",
        ):
            rendering.effective_documents(
                {},
                (common.ROOT / "config.yaml"),
                (common.ROOT / "manifests"),
                None,
                ["gw-routes"],
            )
        # An init container's mount counts as well.
        spec["initContainers"] = [
            dict(
                container,
                name="init",
                volumeMounts=[{"name": "routes", "mountPath": "/r"}],
            )
        ]
        self.manifest([document("Pod", "app", spec=spec)], "20-images.yaml")
        rendering.effective_documents(
            {},
            (common.ROOT / "config.yaml"),
            (common.ROOT / "manifests"),
            None,
            ["gw-routes"],
        )
