"""A release that drops its route or client removes it (backlog item 21, section 3).

The incoming release is authoritative for its own registrations only. The
owner work is recorded before the deletion, so a retry in a fresh process
still rebuilds the owner's imports and restarts it after the file is gone.
"""

import json
import tarfile

import yaml
from deployment import common, deploy, registrations

from helpers.product_fixture import RENAMED, ProductFixture
from helpers.renamed_fixture import RenamedFixture

ROUTE = "routes/inventory.conf"
CLIENT = "clients/inventory"


class RegistrationRemovalTests(ProductFixture):
    install_all = RenamedFixture.install_all
    attempt = RenamedFixture.attempt

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
                list((common.STATE / component).rglob("*"))
                + [common.STATE / "routes" / (component + ".conf")]
                + list((common.STATE / "clients" / component).rglob("*"))
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
        path = common.STATE / owner / "files" / (volume + ".tar")
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
        self.assertTrue((common.STATE / "routes/orders.conf").is_file())
        self.assertTrue((common.STATE / "routes/manual.conf").is_file())
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
                self.assertEqual((common.STATE / ROUTE).exists(), "routes" not in roles)
                self.assertEqual(
                    (common.STATE / CLIENT).exists(), "clients" not in roles
                )
                self.assertEqual(
                    "inventory/client.json" in self.client_index(),
                    "clients" not in roles,
                )
                self.assertEqual("/stock/" in self.route_index(), "routes" not in roles)
                self.assert_siblings_kept()
                self.assertFalse((common.STATE / "pending-operation.json").exists())
                self.assertEqual(
                    (common.STATE / "installed/inventory").read_text(), "1.0.1\n"
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
        both = ["gateway", "login-service"]
        # failure -> (owners left in the record, restarts on the retry). An owner
        # acknowledged before the failure is never restarted again.
        for failure, owners, retry in (
            (
                {"removal_interrupt": True},
                both,
                ["inventory", "login-service", "gateway"],
            ),
            (
                {"archive_failure": "gateway"},
                both,
                ["inventory", "login-service", "gateway"],
            ),
            (
                {"interrupt": ["systemctl", "--user", "daemon-reload"]},
                both,
                ["inventory", "login-service", "gateway"],
            ),
            ({"failure": restart}, ["gateway"], ["inventory", "gateway"]),
            ({"failure": check}, both, ["inventory", "login-service", "gateway"]),
        ):
            with self.subTest(failure=failure):
                self.setUp()
                self.drop("routes", "clients")
                status, _ = self.attempt(self.inventory, **failure)
                self.assertNotEqual(status, 0)
                # The record keeps the work, however much was already deleted.
                self.assertFalse((common.STATE / CLIENT).exists())
                pending = json.loads(
                    (common.STATE / "pending-operation.json").read_text()
                )
                self.assertEqual(pending["component"], "inventory")
                self.assertEqual(pending["owners"], owners)
                status, events = self.attempt(self.inventory)
                self.assertEqual(status, 0, events)
                restarted = [
                    event[-1][len("myproduct-") : -len(".service")]
                    for event in events
                    if event[:3] == ["systemctl", "--user", "restart"]
                ]
                self.assertEqual(restarted, retry)
                self.assertFalse((common.STATE / ROUTE).exists())
                self.assertNotIn("inventory/client.json", self.client_index())
                self.assertNotIn("/stock/", self.route_index())
                self.assertFalse((common.STATE / "pending-operation.json").exists())
                self.assert_siblings_kept()

    def test_uninstall_after_an_upgrade_removed_the_registrations(self):
        self.drop("routes", "clients")
        deploy.install()
        self.process.reset_mock()
        deploy.uninstall()
        # Nothing of inventory is registered any more, so no owner restarts.
        self.assertEqual(self.restarts(), [])
        self.assertFalse((common.STATE / "installed/inventory").exists())
        self.assert_siblings_kept()

    def test_another_component_without_files_is_never_removed(self):
        """Installing orders must not delete inventory's registrations."""
        self.use_root(self.releases["orders"])
        self.process.reset_mock()
        deploy.install()
        self.assertTrue((common.STATE / ROUTE).is_file())
        self.assertTrue((common.STATE / CLIENT / "client.json").is_file())
        self.assertIn("inventory/client.json", self.client_index())
        self.assertIn("/stock/", self.route_index())


class OwnerlessRemovalTests(ProductFixture):
    """A removal whose role nobody accepts has no owner work to record."""

    def test_no_owner_is_never_recorded(self):
        owners = {"routes": None, "clients": "login-service"}
        self.assertEqual(
            registrations.registration_changes(
                {}, owners, state=self.root, removals={"routes/inventory.conf"}
            ),
            set(),
        )
        self.assertEqual(
            registrations.registration_changes(
                {},
                owners,
                state=self.root,
                removals={"routes/inventory.conf", "clients/inventory"},
            ),
            {"login-service"},
        )
