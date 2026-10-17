"""A release that drops its route or client removes it (backlog item 21, section 3).

The incoming release is authoritative for its own registrations only. The
owner work is recorded before the deletion, so a retry in a fresh process
still rebuilds the owner's imports and restarts it after the file is gone.
"""

import json
import tarfile

import yaml
from product_fixture import RENAMED, ProductFixture
from test_renamed_product import RenamedProductTests

from deployment import common, deploy

ROUTE = "routes/inventory.conf"
CLIENT = "clients/inventory"


class RegistrationRemovalTests(ProductFixture):
    install_all = RenamedProductTests.install_all
    attempt = RenamedProductTests.attempt

    def setUp(self):
        super().setUp()
        self.write_product(RENAMED)
        self.releases, _ = self.install_all()
        self.inventory = self.releases["inventory"]
        self.use_root(self.inventory)
        self.sibling = self.snapshot("orders")

    def snapshot(self, component):
        return {
            str(path): path.read_bytes()
            for path in (
                list((common.HOME / component).rglob("*"))
                + [common.HOME / "routes" / (component + ".conf")]
                + list((common.HOME / "clients" / component).rglob("*"))
            )
            if path.is_file()
        }

    def drop(self, *roles, version="1.0.1"):
        """Make the unpacked inventory release a newer one without these roles."""
        descriptor = yaml.safe_load((self.inventory / "bundle.yaml").read_text())
        descriptor["version"] = version
        for role in roles:
            descriptor[role] = None
            filename = "route.conf" if role == "routes" else "client.yaml"
            path = self.inventory / "components/inventory" / filename
            if path.exists():
                path.unlink()
        (self.inventory / "bundle.yaml").write_text(yaml.safe_dump(descriptor))

    def imported(self, owner, volume, member):
        """Read one file from the import archive an owner receives."""
        path = common.HOME / owner / "files" / (volume + ".tar")
        with tarfile.open(str(path)) as tar:
            stream = tar.extractfile(member)
            assert stream is not None, member
            return stream.read().decode("utf-8")

    def client_index(self):
        return json.loads(
            self.imported("login-service", "login-service-clients", "installed.json")
        )

    def route_index(self):
        return self.imported("gateway", "gateway-routes", "installed.conf")

    def assert_siblings_kept(self):
        self.assertEqual(self.snapshot("orders"), self.sibling)
        self.assertIn("orders/client.json", self.client_index())
        self.assertTrue((common.HOME / "routes/orders.conf").is_file())
        self.assertTrue((common.HOME / "routes/manual.conf").is_file())
        self.assertIn("/orders/", self.route_index())
        self.assertIn("/manual/", self.route_index())

    def test_exact_removals_and_owner_restarts(self):
        for roles, expected in (
            ((), ["inventory"]),
            (("routes",), ["inventory", "gateway"]),
            (("clients",), ["inventory", "login-service"]),
            (("routes", "clients"), ["inventory", "login-service", "gateway"]),
        ):
            with self.subTest(roles=roles):
                self.setUp()
                self.drop(*roles)
                self.process.reset_mock()
                deploy.install()
                self.assertEqual(self.restarts(), expected)
                self.assertEqual((common.HOME / ROUTE).exists(), "routes" not in roles)
                self.assertEqual(
                    (common.HOME / CLIENT).exists(), "clients" not in roles
                )
                self.assertEqual(
                    "inventory/client.json" in self.client_index(),
                    "clients" not in roles,
                )
                self.assertEqual("/stock/" in self.route_index(), "routes" not in roles)
                self.assert_siblings_kept()
                self.assertFalse((common.HOME / "pending-operation.json").exists())
                self.assertEqual(
                    (common.HOME / "installed/inventory").read_text(), "1.0.1\n"
                )

    def test_repeating_the_same_release_changes_nothing_more(self):
        self.drop("routes", "clients")
        deploy.install()
        self.process.reset_mock()
        deploy.install()
        # Nothing left to remove: no owner restarts, only the component itself.
        self.assertEqual(set(self.restarts()) - {"inventory"}, set())

    def test_failures_after_deletion_finish_in_a_fresh_process(self):
        restart = ["systemctl", "--user", "restart", "myproduct-gateway.service"]
        check = [
            "systemctl",
            "--user",
            "is-active",
            "--quiet",
            "myproduct-login-service.service",
        ]
        for failure in (
            {"archive_failure": "gateway"},
            {"interrupt": ["systemctl", "--user", "daemon-reload"]},
            {"failure": restart},
            {"failure": check},
        ):
            with self.subTest(failure=failure):
                self.setUp()
                self.drop("routes", "clients")
                status, _ = self.attempt(self.inventory, **failure)
                self.assertNotEqual(status, 0)
                # The registrations are already gone; the record keeps the work.
                self.assertFalse((common.HOME / ROUTE).exists())
                self.assertFalse((common.HOME / CLIENT).exists())
                pending = json.loads(
                    (common.HOME / "pending-operation.json").read_text()
                )
                self.assertEqual(pending["component"], "inventory")
                self.assertTrue(pending["owners"])
                status, events = self.attempt(self.inventory)
                self.assertEqual(status, 0, events)
                restarted = [
                    event[-1][len("myproduct-") : -len(".service")]
                    for event in events
                    if event[:3] == ["systemctl", "--user", "restart"]
                ]
                self.assertEqual(restarted[0], "inventory")
                self.assertTrue(set(pending["owners"]) <= set(restarted))
                self.assertNotIn("orders", restarted)
                self.assertNotIn("inventory/client.json", self.client_index())
                self.assertNotIn("/stock/", self.route_index())
                self.assertFalse((common.HOME / "pending-operation.json").exists())
                self.assert_siblings_kept()

    def test_uninstall_after_an_upgrade_removed_the_registrations(self):
        self.drop("routes", "clients")
        deploy.install()
        self.process.reset_mock()
        deploy.uninstall()
        # Nothing of inventory is registered any more, so no owner restarts.
        self.assertEqual(self.restarts(), [])
        self.assertFalse((common.HOME / "installed/inventory").exists())
        self.assert_siblings_kept()

    def test_another_component_without_files_is_never_removed(self):
        """Installing orders must not delete inventory's registrations."""
        self.use_root(self.releases["orders"])
        self.process.reset_mock()
        deploy.install()
        self.assertTrue((common.HOME / ROUTE).is_file())
        self.assertTrue((common.HOME / CLIENT / "client.json").is_file())
        self.assertIn("inventory/client.json", self.client_index())
        self.assertIn("/stock/", self.route_index())
