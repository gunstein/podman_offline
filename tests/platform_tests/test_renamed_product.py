"""A fully renamed product works through declarations alone (backlog item 20)."""

import json
import shutil

import yaml
from deployment import catalog, common, deploy

from helpers.product_fixture import DEMO_NAMES, PEM, RENAMED, ProductFixture
from helpers.renamed_fixture import RenamedFixture


class RenamedProductTests(RenamedFixture):
    """gateway, login-service, orders, inventory and manual; no demo names anywhere."""

    def test_dev_prepare_renders_catalog_with_renamed_owners_and_clients(self):
        self.provide_credentials(RENAMED, common.BUILD / "dev")
        deploy.prepare()
        text = (common.BUILD / "install.yaml").read_text()
        pods = [
            doc["metadata"]["name"]
            for doc in yaml.safe_load_all(text)
            if doc["kind"] == "Pod"
        ]
        # Dependency order with manifest order kept inside each component.
        self.assertEqual(
            pods,
            [
                "gateway-proxy",
                "login-service-server",
                "orders-postgres",
                "orders-web",
                "inventory-web",
                "manual-web",
            ],
        )
        resource_names = [doc["metadata"]["name"] for doc in yaml.safe_load_all(text)]
        for name in DEMO_NAMES:
            self.assertFalse(
                any(
                    value == name or value.startswith(name + "-")
                    for value in resource_names
                )
            )
        self.assertIn("hostname: shop.test", text)
        dev = common.BUILD / "dev"
        self.assertEqual(
            sorted(path.name for path in (dev / "routes").iterdir()),
            ["inventory.conf", "login-service.conf", "manual.conf", "orders.conf"],
        )
        registration = json.loads((dev / "clients/orders/client.json").read_text())
        self.assertEqual(registration["Id"], "orders-web")
        self.assertEqual(
            registration["RedirectUris"],
            ["https://shop.test:9443/orders/auth/callback"],
        )
        self.assertEqual(registration["Scopes"], ["openid", "profile", "orders-web"])
        # Public settings are inherited from the declared gateway, as in production.
        orders = yaml.safe_load((dev / "orders/config.yaml").read_text())
        self.assertEqual(orders["PUBLIC_ORIGIN"], "https://shop.test:9443")
        self.assertNotIn(
            "PUBLIC_ORIGIN", yaml.safe_load((dev / "manual/config.yaml").read_text())
        )

    def test_offline_install_without_source_uses_declared_owners_and_order(self):
        _, restarts = self.install_all()
        self.assertFalse(self.source.exists())
        self.assertEqual(restarts["gateway"], ["gateway"])
        self.assertEqual(restarts["login-service"], ["login-service", "gateway"])
        # Owners restart after the component they serve: client before route owner.
        self.assertEqual(restarts["orders"], ["orders", "login-service", "gateway"])
        self.assertEqual(
            restarts["inventory"], ["inventory", "login-service", "gateway"]
        )
        self.assertEqual(restarts["manual"], ["manual", "gateway"])
        installed = catalog.load_installed_metadata(common.STATE)
        self.assertEqual(installed["orders"]["clients"], "login-service")
        self.assertEqual(installed["gateway"]["accepts"], {"routes": "gateway-routes"})
        index = json.loads((common.STATE / "clients/orders/client.json").read_text())
        self.assertEqual(index["Id"], "orders-web")
        orders_config = yaml.safe_load(
            (common.STATE / "orders/config.yaml").read_text()
        )
        self.assertEqual(orders_config["PUBLIC_ORIGIN"], "https://shop.test:9443")
        self.assertTrue(
            (common.STATE / "orders/credentials/database/password").is_file()
        )
        for name in DEMO_NAMES:
            self.assertFalse((common.STATE / name).exists())
            self.assertFalse((common.STATE / "installed" / name).exists())

    def test_exact_restart_sets_and_sibling_isolation(self):
        releases, _ = self.install_all()
        orders = releases["orders"]
        self.use_root(orders)
        sibling = {
            path: path.read_bytes()
            for path in (common.STATE / "inventory").rglob("*")
            if path.is_file()
        }
        sibling_client = (common.STATE / "clients/inventory/client.json").read_bytes()
        certificate = common.STATE / "orders/credentials/client/client.crt"
        for index, (route_changed, client_changed, expected) in enumerate(
            (
                (False, False, ["orders"]),
                (True, False, ["orders", "gateway"]),
                (False, True, ["orders", "login-service"]),
                (True, True, ["orders", "login-service", "gateway"]),
            )
        ):
            with self.subTest(route=route_changed, client=client_changed):
                if route_changed:
                    route = orders / "components/orders/route.conf"
                    route.write_text(
                        route.read_text() + "# change " + str(index) + "\n"
                    )
                if client_changed:
                    certificate.write_text(
                        PEM.replace("Y2VydA==", "Y2VydA" + str(index) + "=")
                    )
                self.process.reset_mock()
                deploy.install()
                self.assertEqual(self.restarts(), expected)
                self.assertNotIn("inventory", self.restarts())
        self.assertEqual(
            {
                path: path.read_bytes()
                for path in (common.STATE / "inventory").rglob("*")
                if path.is_file()
            },
            sibling,
        )
        self.assertEqual(
            (common.STATE / "clients/inventory/client.json").read_bytes(),
            sibling_client,
        )

    def test_uninstall_keeps_sibling_client_and_reverse_dependencies(self):
        releases, _ = self.install_all()
        self.use_root(releases["login-service"])
        with self.assertRaisesRegex(
            common.DeployError, "still required by: inventory, orders"
        ):
            deploy.uninstall()
        self.use_root(releases["inventory"])
        self.process.reset_mock()
        deploy.uninstall()
        self.assertEqual(self.restarts(), ["login-service", "gateway"])
        self.assertFalse((common.STATE / "clients/inventory").exists())
        self.assertTrue((common.STATE / "clients/orders/client.json").is_file())
        self.assertTrue((common.STATE / "inventory/config.yaml").is_file())
        self.assertFalse((common.STATE / "metadata/inventory.json").exists())
        # The gateway's newer release must still satisfy installed dependents.
        gateway = releases["gateway"]
        descriptor = yaml.safe_load((gateway / "bundle.yaml").read_text())
        (gateway / "bundle.yaml").write_text(
            yaml.safe_dump(dict(descriptor, version="2.0.0"))
        )
        self.use_root(gateway)
        self.process.reset_mock()
        with self.assertRaisesRegex(common.DeployError, "dependency for login-service"):
            deploy.install()
        self.process.assert_not_called()

    def test_owner_failure_retries_in_fresh_process_with_renamed_ids(self):
        releases = self.install_shared()
        self.use_root(releases["orders"])
        deploy.init_config("orders")
        failure = [
            "systemctl",
            "--user",
            "is-active",
            "--quiet",
            "myproduct-login-service.service",
        ]
        status, events = self.attempt(releases["orders"], failure=failure)
        self.assertEqual(status, 1)
        pending = json.loads((common.STATE / "pending-operation.json").read_text())
        self.assertEqual(pending["component"], "orders")
        self.assertEqual(pending["owners"], ["gateway", "login-service"])
        self.assertFalse((common.STATE / "installed/orders").exists())
        status, events = self.attempt(releases["orders"])
        self.assertEqual(status, 0, events)
        restarted = [
            event[-1]
            for event in events
            if event[:3] == ["systemctl", "--user", "restart"]
        ]
        self.assertEqual(
            restarted,
            [
                "myproduct-orders.service",
                "myproduct-login-service.service",
                "myproduct-gateway.service",
            ],
        )
        self.assertFalse((common.STATE / "pending-operation.json").exists())
        self.assertEqual((common.STATE / "installed/orders").read_text(), "1.0.0\n")

    def test_pending_owner_work_finishes_with_a_release_that_drops_the_role(self):
        """Unfinished gateway work is completed even if the next release has no route."""
        releases = self.install_shared()
        manual = releases["manual"]
        self.use_root(manual)
        deploy.init_config("manual")
        failure = ["systemctl", "--user", "restart", "myproduct-gateway.service"]
        status, _ = self.attempt(manual, failure=failure)
        self.assertEqual(status, 1)
        pending = json.loads((common.STATE / "pending-operation.json").read_text())
        self.assertEqual(pending["owners"], ["gateway"])
        # A newer manual release no longer declares a route.
        descriptor = yaml.safe_load((manual / "bundle.yaml").read_text())
        (manual / "bundle.yaml").write_text(
            yaml.safe_dump(dict(descriptor, routes=None, version="1.0.1"))
        )
        (manual / "components/manual/route.conf").unlink()
        status, events = self.attempt(manual)
        self.assertEqual(status, 0, events)
        self.assertIn(
            ["systemctl", "--user", "restart", "myproduct-gateway.service"], events
        )
        self.assertFalse((common.STATE / "pending-operation.json").exists())
        self.assertEqual((common.STATE / "installed/manual").read_text(), "1.0.1\n")

    def test_lost_password_with_existing_renamed_volume_is_refused(self):
        """The renamed database volume is inspected by its name before any write."""
        releases = self.install_shared()
        self.use_root(releases["orders"])
        deploy.init_config("orders")
        self.volumes.add("orders-data")
        before = self.files_under(common.STATE)
        self.process.reset_mock()
        with self.assertRaisesRegex(
            common.DeployError,
            "Missing database password file .*orders/credentials/database/password "
            "with existing volume orders-data",
        ):
            deploy.install()
        self.assertEqual(
            self.commands(), [["podman", "volume", "exists", "orders-data"]]
        )
        self.assertEqual(self.files_under(common.STATE), before)


class UnsupportedKindTests(ProductFixture):
    """A Deployment can neither take another component's name nor skip preflight."""

    def setUp(self):
        super().setUp()
        self.write_product(RENAMED)

    def test_unsupported_kinds_in_a_release_fail_before_host_commands(self):
        releases = self.build_and_unpack()
        shutil.rmtree(self.source)
        self.provide_credentials(RENAMED, common.STATE)
        self.install(releases["gateway"])
        self.install(releases["login-service"])
        release = releases["orders"]
        manifest = release / "components/orders/manifests/10-resources.yaml"
        original = manifest.read_text()
        documents = list(yaml.safe_load_all(original))
        database = next(
            doc for doc in documents if doc["metadata"]["name"] == "orders-postgres"
        )
        for name, spec in (
            ("gateway-stolen", documents[0]["spec"]),
            ("orders-postgres", database["spec"]),
        ):
            with self.subTest(name=name):
                deployment = {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {"name": name},
                    "spec": {"template": {"spec": spec}},
                }
                manifest.write_text(
                    original + "---\n" + yaml.safe_dump(deployment, sort_keys=False)
                )
                self.use_root(release)
                deploy.init_config("orders")
                self.volumes.add("orders-data")
                before = self.files_under(common.STATE)
                self.process.reset_mock()
                with self.assertRaisesRegex(
                    common.DeployError,
                    "10-resources.yaml: unsupported resource kind 'Deployment'",
                ):
                    deploy.install()
                self.assertEqual(self.commands(), [])
                self.assertEqual(self.files_under(common.STATE), before)
