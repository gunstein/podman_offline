"""./deploy validate: every component's first finding, with no writes or commands.

Backlog item 23. The command reuses the lifecycle's validation (effective
documents, PostgreSQL layout, staging, install_checks), so prepare and install
cannot disagree with it.
"""

import copy
import shutil
from unittest import mock

import yaml
from product_fixture import RENAMED, ProductFixture
from test_deploy import DeployFixture, document
from test_validation_order import CASES, broken_orders

from deployment import cli, common, deploy

MANIFEST = "components/orders/manifests/10-resources.yaml"


class SourceValidationTests(ProductFixture):
    def setUp(self):
        super().setUp()
        self.write_product(RENAMED)
        self.dev = common.BUILD / "dev"
        self.provide_credentials(RENAMED, self.dev)

    def validate(self, pattern=None):
        """Run the command; with a pattern, require a refusal and return its text."""
        before = self.files_under(self.root)
        self.process.reset_mock()
        error = ""
        if pattern is None:
            deploy.validate()
        else:
            with self.assertRaisesRegex(common.DeployError, pattern) as failure:
                deploy.validate()
            error = str(failure.exception)
        # Nothing written anywhere, and no Podman or systemd call.
        self.assertEqual(self.files_under(self.root), before)
        self.assertEqual(self.commands(), [])
        return error

    def write_orders(self, documents):
        (self.source / MANIFEST).write_text(yaml.safe_dump_all(documents))

    def orders_defaults(self, change):
        path = self.source / "components/orders/config.defaults.yaml"
        defaults = yaml.safe_load(path.read_text())
        change(defaults)
        path.write_text(yaml.safe_dump(defaults))

    def test_valid_catalog_passes(self):
        self.validate()
        self.assertIn(
            "[OK] validated gateway, login-service, orders, inventory, manual",
            self.stdout.getvalue(),
        )

    def test_manifest_findings_name_the_component(self):
        for case in CASES:
            with self.subTest(case=case):
                documents, message = broken_orders(case)
                self.write_orders(documents)
                error = self.validate("1 validation finding")
                self.assertRegex(error, "\n  orders: .*" + message)

    def test_placeholder_only_in_an_init_container(self):
        documents = copy.deepcopy(RENAMED["orders"]["manifests"])
        documents[2]["spec"]["initContainers"] = [
            {
                "name": "prepare",
                "image": "localhost/shop-app:1",
                "imagePullPolicy": "Never",
                "env": [{"name": "SCHEMA", "value": "@@ORDERS_SCHEMA@@"}],
            }
        ]
        self.write_orders(documents)
        # Placeholders are checked while dev config is assembled, as prepare does.
        self.validate("Missing ORDERS_SCHEMA in .*orders/config.yaml")

    def test_config_and_source_findings(self):
        defaults = self.source / "components/orders/config.defaults.yaml"
        original = defaults.read_text()
        for name, change, message in (
            (
                "unused id",
                lambda d: d["SECRET_FILES"].update(
                    {"orders-spare": [{"path": "credentials/client"}]}
                ),
                ".*SECRET_FILES.orders-spare in config.yaml is not used",
            ),
            (
                "missing source",
                lambda d: d["SECRET_FILES"].update(
                    {"orders-client": [{"path": "credentials/elsewhere"}]}
                ),
                ".*Missing .*credentials/elsewhere \\(SECRET_FILES.orders-client\\)",
            ),
        ):
            with self.subTest(name=name):
                defaults.write_text(original)
                self.orders_defaults(change)
                self.validate("orders: " + message)

    def test_secret_source_directory_is_reported_without_reading(self):
        nested = self.dev / "orders/credentials/client/nested"
        nested.mkdir()
        self.validate("orders: SECRET_FILES.orders-client: .*nested is a directory")

    def test_undefined_config_map(self):
        documents = copy.deepcopy(RENAMED["orders"]["manifests"])
        container = documents[2]["spec"]["containers"][0]
        container["envFrom"] = [{"configMapRef": {"name": "orders-settings"}}]
        self.write_orders(documents)
        self.validate("orders: .*ConfigMap 'orders-settings', but it does not exist")

    def test_invalid_client_and_missing_certificate(self):
        client = self.source / "components/orders/client.yaml"
        client.write_text("id: orders-web\nbase_path: no-slash\nscopes: [openid]\n")
        self.validate("registrations: Invalid public client descriptor")
        client.write_text(yaml.safe_dump(RENAMED["orders"]["client"]))
        (self.dev / "orders/credentials/client/client.crt").unlink()
        self.validate(
            "registrations: Missing public client certificate .*client.crt "
            "\\(certificate in .*orders/client.yaml\\)"
        )

    def test_every_component_is_reported_in_one_run(self):
        documents, _ = broken_orders("undefined mount")
        self.write_orders(documents)
        manual = self.source / "components/manual/manifests/10-resources.yaml"
        manual.write_text(manual.read_text().replace("Never", "IfNotPresent"))
        error = self.validate("2 validation finding")
        self.assertRegex(error, "\n  orders: .*undefined volume")
        self.assertRegex(error, "\n  manual: .*imagePullPolicy: Never")

    def test_prepare_and_validate_report_the_same_finding(self):
        for case in CASES:
            with self.subTest(case=case):
                documents, _ = broken_orders(case)
                self.write_orders(documents)
                with self.assertRaises(common.DeployError) as prepared:
                    deploy.prepare()
                error = self.validate("orders: ")
                self.assertIn(str(prepared.exception), error)

    def test_cli_exit_codes(self):
        with mock.patch.object(cli.sys, "argv", ["deploy", "validate"]):
            self.assertEqual(cli.main(), 0)
        documents, _ = broken_orders("undefined mount")
        self.write_orders(documents)
        with mock.patch.object(cli.sys, "argv", ["deploy", "validate"]):
            self.assertEqual(cli.main(), 1)
        self.assertIn("orders: ", self.stderr.getvalue())
        with mock.patch.object(cli.sys, "argv", ["deploy", "validate", "orders"]):
            self.assertEqual(cli.main(), 2)


class BundleValidationTests(ProductFixture):
    """In an unpacked bundle: the component against the installed set and config."""

    def setUp(self):
        super().setUp()
        self.write_product(RENAMED)
        self.releases_by_name = self.build_and_unpack()
        shutil.rmtree(self.source)
        self.provide_credentials(RENAMED, common.HOME)

    def validate(self, release, pattern=None):
        self.use_root(release)
        before = self.files_under(self.root)
        self.process.reset_mock()
        if pattern is None:
            deploy.validate()
        else:
            with self.assertRaisesRegex(common.DeployError, pattern):
                deploy.validate()
        self.assertEqual(self.files_under(self.root), before)
        self.assertEqual(self.commands(), [])

    def test_dependencies_config_and_manifests_as_install(self):
        orders = self.releases_by_name["orders"]
        self.validate(orders, "Install the separate gateway bundle")
        for name in ("gateway", "login-service"):
            self.install(self.releases_by_name[name])
        self.use_root(orders)
        self.validate(
            orders, "Missing .*orders/config.yaml; run ./deploy init-config orders"
        )
        deploy.init_config("orders")
        self.validate(orders)
        self.assertIn("[OK] validated orders", self.stdout.getvalue())
        documents, message = broken_orders("online pull policy")
        (orders / MANIFEST).write_text(yaml.safe_dump_all(documents))
        self.validate(orders, "orders: .*" + message)

    def test_missing_image_archive(self):
        for name in ("gateway", "login-service"):
            self.install(self.releases_by_name[name])
        orders = self.releases_by_name["orders"]
        self.use_root(orders)
        deploy.init_config("orders")
        (orders / "images/images.tar").unlink()
        self.validate(orders, "orders: Missing image archive")


class StandaloneValidationTests(DeployFixture):
    def test_fixture_manifests_against_config(self):
        self.config["SECRET_FILES"] = {
            "db": [{"path": "credentials", "generate": ["password"]}]
        }
        self.write_config()
        pod = document(
            "Pod",
            "app",
            spec={
                "containers": [
                    {
                        "name": "web",
                        "image": "localhost/app:1",
                        "imagePullPolicy": "Never",
                        "volumeMounts": [{"name": "db", "mountPath": "/x"}],
                    }
                ],
                "volumes": [{"name": "db", "secret": {"secretName": "db"}}],
            },
        )
        self.manifest([pod], "20-images.yaml")
        deploy.validate()
        self.assertIn("[OK] validated manifests", self.stdout.getvalue())
        pod["spec"]["containers"][0]["image"] = "app:1"
        self.manifest([pod], "20-images.yaml")
        with self.assertRaisesRegex(
            common.DeployError, "manifests: Image app:1 must be fully qualified"
        ):
            deploy.validate()
        self.process.assert_not_called()
        self.assertFalse((common.CONFIG.parent / "credentials").exists())
        self.assertFalse(common.BUILD.exists())
