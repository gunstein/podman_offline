"""A fully renamed product works through declarations alone (backlog item 20)."""

import json
import shutil
import subprocess
import sys

import yaml
from product_fixture import DEMO_NAMES, PEM, RENAMED, ProductFixture
from test_retry import DRIVER, REAL_RUN, SOURCE

from deployment import catalog, common, deploy


class RenamedProductTests(ProductFixture):
    """gateway, login-service, orders, inventory and manual; no demo names anywhere."""

    def setUp(self):
        super().setUp()
        self.write_product(RENAMED)

    def install_all(self):
        """Build, delete the source checkout, then install offline in dependency order."""
        releases = self.build_and_unpack()
        shutil.rmtree(self.source)
        self.provide_credentials(RENAMED, common.HOME)
        restarts = {}
        for name in ("gateway", "login-service", "orders", "inventory", "manual"):
            restarts[name] = self.install(releases[name])
        return releases, restarts

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
        for name in DEMO_NAMES:
            self.assertNotIn(name, text)
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
        installed = catalog.load_installed_metadata(common.HOME)
        self.assertEqual(installed["orders"]["clients"], "login-service")
        self.assertEqual(installed["gateway"]["accepts"], {"routes": "gateway-routes"})
        index = json.loads((common.HOME / "clients/orders/client.json").read_text())
        self.assertEqual(index["Id"], "orders-web")
        orders_config = yaml.safe_load((common.HOME / "orders/config.yaml").read_text())
        self.assertEqual(orders_config["PUBLIC_ORIGIN"], "https://shop.test:9443")
        self.assertTrue(
            (common.HOME / "orders/credentials/database/password").is_file()
        )
        for name in DEMO_NAMES:
            self.assertFalse((common.HOME / name).exists())
            self.assertFalse((common.HOME / "installed" / name).exists())

    def test_exact_restart_sets_and_sibling_isolation(self):
        releases, _ = self.install_all()
        orders = releases["orders"]
        self.use_root(orders)
        sibling = {
            path: path.read_bytes()
            for path in (common.HOME / "inventory").rglob("*")
            if path.is_file()
        }
        sibling_client = (common.HOME / "clients/inventory/client.json").read_bytes()
        certificate = common.HOME / "orders/credentials/client/client.crt"
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
                for path in (common.HOME / "inventory").rglob("*")
                if path.is_file()
            },
            sibling,
        )
        self.assertEqual(
            (common.HOME / "clients/inventory/client.json").read_bytes(), sibling_client
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
        self.assertFalse((common.HOME / "clients/inventory").exists())
        self.assertTrue((common.HOME / "clients/orders/client.json").is_file())
        self.assertTrue((common.HOME / "inventory/config.yaml").is_file())
        self.assertFalse((common.HOME / "metadata/inventory.json").exists())
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
        releases = self.build_and_unpack()
        shutil.rmtree(self.source)
        self.provide_credentials(RENAMED, common.HOME)
        for name in ("gateway", "login-service"):
            self.install(releases[name])
        self.use_root(releases["orders"])
        deploy.init_config("orders")

        def attempt(**options):
            parameters = dict(
                root=str(releases["orders"]),
                home=str(common.HOME),
                source=str(SOURCE),
                record=str(self.root / "attempt.json"),
                action="install",
                **options,
            )
            result = REAL_RUN(
                [sys.executable, "-B", str(DRIVER)],
                input=json.dumps(parameters),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                check=False,
            )
            events = json.loads((self.root / "attempt.json").read_text())["events"]
            return result.returncode, events

        failure = [
            "systemctl",
            "--user",
            "is-active",
            "--quiet",
            "myproduct-login-service.service",
        ]
        status, events = attempt(failure=failure)
        self.assertEqual(status, 1)
        pending = json.loads((common.HOME / "pending-operation.json").read_text())
        self.assertEqual(pending["component"], "orders")
        self.assertEqual(pending["owners"], ["gateway", "login-service"])
        self.assertFalse((common.HOME / "installed/orders").exists())
        status, events = attempt()
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
        self.assertFalse((common.HOME / "pending-operation.json").exists())
        self.assertEqual((common.HOME / "installed/orders").read_text(), "1.0.0\n")
