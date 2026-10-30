"""A minimal worker, and adding or removing a service through YAML only."""

import copy
import shutil
import tarfile
import warnings
from unittest import mock

import bundle
import yaml
from deployment import common, deploy, registrations, validation

from helpers.product_fixture import RENAMED, WORKER, ProductFixture, pod, route

REPORTS = {
    "catalog": {},
    "manifests": [pod("reports-web", "localhost/reports:1")],
    "route": route("reports", "/reports", "reports-web:8080"),
}


class MinimalWorkerTests(ProductFixture):
    """No gateway, Identity, public URL, database, certificates, config or apps/."""

    def test_worker_prepares_bundles_installs_and_uninstalls(self):
        self.write_product(WORKER)
        self.assertFalse((self.source / "apps").exists())
        self.assertFalse((self.source / "config").exists())
        deploy.prepare()
        self.assertIn("worker-job", (common.BUILD / "install.yaml").read_text())
        self.assertEqual(
            yaml.safe_load((common.BUILD / "dev/worker/config.yaml").read_text()), {}
        )
        self.assertNotIn(
            ["podman", "volume", "exists"], [c[:3] for c in self.commands()]
        )
        releases = self.build_and_unpack()
        self.assertIn(
            [
                "podman",
                "pull",
                "--policy=always",
                "registry.example.test/team/worker:1",
            ],
            self.commands(),
        )
        shutil.rmtree(self.source)
        self.assertEqual(self.install(releases["worker"]), ["worker"])
        for name in ("routes", "clients", "metadata/gateway.json"):
            self.assertFalse((common.STATE / name).exists())
        self.process.reset_mock()
        deploy.uninstall(delete_data=True)
        self.assertEqual(self.restarts(), [])
        self.assertFalse((common.STATE / "installed/worker").exists())
        self.assertFalse((common.STATE / "metadata/worker.json").exists())


class ProductNameTests(ProductFixture):
    """product: in bundles.yaml names everything the installation creates."""

    def installed_names(self):
        return sorted(
            str(path.relative_to(common.STATE))
            for path in common.STATE.rglob("*")
            if path.is_file()
        )

    def installed_files(self):
        """Every file under the service home with its bytes."""
        return {
            name: (common.STATE / name).read_bytes() for name in self.installed_names()
        }

    def other_product_release(self):
        """Build worker 1.0.1 as product other-shop; the source is replaced."""
        shutil.rmtree(self.source)
        self.product_name = "other-shop"
        self.write_product(WORKER, version="1.0.1")
        release = self.build_and_unpack()["worker"]
        self.use_root(release)
        self.process.reset_mock()
        return release

    def test_product_name_reaches_every_installed_name(self):
        self.product_name = "hubbabubba"
        self.write_product(WORKER)
        deploy.prepare()
        releases = self.build_and_unpack()
        self.assertEqual(
            (self.source / "dist/current-bundles.txt").read_text(),
            "hubbabubba-worker-1.0.0-offline.tar.gz\n",
        )
        shutil.rmtree(self.source)
        self.assertEqual(self.install(releases["worker"]), ["worker"])
        self.assertIn(
            ["systemctl", "--user", "restart", "hubbabubba-worker.service"],
            self.commands(),
        )
        units = common.QUADLET_DIR
        self.assertEqual(
            sorted(path.name for path in units.iterdir()),
            ["hubbabubba-worker.kube", "hubbabubba-worker.yaml", "hubbabubba.network"],
        )
        kube = (units / "hubbabubba-worker.kube").read_text()
        self.assertIn("Yaml=hubbabubba-worker.yaml\n", kube)
        self.assertIn("Network=hubbabubba.network\n", kube)
        self.assertIn(
            "NetworkName=hubbabubba\n", (units / "hubbabubba.network").read_text()
        )
        for name in self.installed_names():
            self.assertNotIn("myproduct", name)
            self.assertNotIn("myproduct", (common.STATE / name).read_text())
        self.assertNotIn("myproduct", str(self.commands()))
        self.process.reset_mock()
        deploy.uninstall()
        self.assertIn(
            ["systemctl", "--user", "stop", "hubbabubba-worker.service"],
            self.commands(),
        )

    def test_another_product_is_refused_before_any_write(self):
        """One service user runs one product; units of two products would mix."""
        self.product_name = "hubbabubba"
        self.write_product(WORKER)
        self.install(self.build_and_unpack()["worker"])
        before = self.installed_files()
        self.other_product_release()
        for action in (deploy.install, deploy.uninstall, validation.validate_bundle):
            with self.subTest(action=action.__name__):
                with self.assertRaisesRegex(
                    common.DeployError,
                    "already runs product hubbabubba; this bundle belongs to other-shop",
                ):
                    action()
        self.assertEqual(self.commands(), [])
        self.assertEqual(self.installed_files(), before)

    def test_unfinished_last_uninstall_stays_with_its_product(self):
        """Once the last metadata is gone, the pending record names the product."""
        self.product_name = "hubbabubba"
        self.write_product(WORKER)
        release = self.build_and_unpack()["worker"]
        self.install(release)
        with mock.patch.object(
            registrations, "clear_pending", side_effect=OSError("disk full")
        ):
            with self.assertRaises(OSError):
                deploy.uninstall()
        self.assertFalse((common.STATE / "metadata/worker.json").exists())
        record = (common.STATE / "pending-operation.json").read_bytes()
        self.assertIn(b'"product": "hubbabubba"', record)
        self.other_product_release()
        with self.assertRaisesRegex(
            common.DeployError,
            "Pending uninstall of worker belongs to product hubbabubba; "
            "this bundle belongs to other-shop",
        ):
            deploy.uninstall()
        self.assertEqual(self.commands(), [])
        self.assertEqual((common.STATE / "pending-operation.json").read_bytes(), record)
        # The product's own bundle still finishes the uninstall.
        self.use_root(release)
        deploy.uninstall()
        self.assertFalse((common.STATE / "pending-operation.json").exists())


class ClientIdentityTests(ProductFixture):
    """client.yaml's id and base_path must match the app's variables and route."""

    def product(self, variable_value=None, route_path=None, environment=True):
        product = copy.deepcopy(RENAMED)
        orders = product["orders"]
        if environment:
            orders["client"]["environment"] = {"id": "APP_ID", "base_path": "BASE_PATH"}
        if variable_value is not None:
            for document in orders["manifests"]:
                for container in document.get("spec", {}).get("containers", []):
                    for entry in container.get("env", []):
                        if entry["name"] == "APP_ID":
                            entry["value"] = variable_value
        if route_path is not None:
            orders["route"] = route("orders", route_path, "orders-web:8000")
        self.write_product(product)
        self.provide_credentials(product, common.BUILD / "dev")

    def refused(self, pattern):
        """prepare and validate report the same finding before any dev output."""
        for action in (deploy.prepare, validation.validate):
            with self.subTest(action=action.__name__):
                with self.assertRaisesRegex(common.DeployError, pattern):
                    action()
        self.assertFalse((common.BUILD / "install.yaml").exists())

    def test_matching_declaration_passes(self):
        self.product()
        deploy.prepare()
        self.assertTrue((common.BUILD / "install.yaml").exists())

    def test_variable_that_differs_from_client_yaml_is_refused(self):
        self.product(variable_value="orders")
        self.refused(
            "orders/client.yaml: id is 'orders-web', but the manifests set APP_ID "
            "to 'orders'"
        )

    def test_route_without_the_base_path_is_refused(self):
        self.product(route_path="/shop")
        self.refused("orders/route.conf has no location for base_path /orders")

    def test_variables_are_compared_only_when_declared(self):
        """Products whose apps use other variables are not checked against them."""
        self.product(variable_value="orders", environment=False)
        deploy.prepare()

    def test_invalid_environment_declaration_is_refused(self):
        product = copy.deepcopy(RENAMED)
        product["orders"]["client"]["environment"] = {"client": "APP_ID"}
        self.write_product(product)
        self.provide_credentials(product, common.BUILD / "dev")
        self.refused("Invalid public client descriptor")


class SharedSettingTests(ProductFixture):
    """shares: an owner's custom settings travel and are compared like PUBLIC_ORIGIN."""

    def product(self, shares=("SHOP_REGION",), version="1.0.0"):
        """gateway owns SHOP_REGION; login-service (public_from gateway) uses it."""
        product = copy.deepcopy(RENAMED)
        gateway, login = product["gateway"], product["login-service"]
        gateway["catalog"]["shares"] = list(shares)
        gateway["defaults"].update(SHOP_REGION="eu", LOCAL_NOTE="gateway")
        login["defaults"] = {"SHOP_REGION": "us", "LOCAL_NOTE": "login"}
        environment = login["manifests"][0]["spec"]["containers"][0]["env"]
        environment += [
            {"name": "REGION", "value": "@@SHOP_REGION@@"},
            {"name": "NOTE", "value": "@@LOCAL_NOTE@@"},
        ]
        gateway["manifests"][0]["spec"]["containers"][0]["env"].append(
            {"name": "NOTE", "value": "@@LOCAL_NOTE@@"}
        )
        self.write_product(product, version=version)
        return product

    def edit(self, component, **values):
        path = common.STATE / component / "config.yaml"
        config = yaml.safe_load(path.read_text())
        config.update(values)
        for key in [key for key, value in values.items() if value is None]:
            del config[key]
        path.write_text(yaml.safe_dump(config))

    def install_gateway_and_init_login(self, region="nordic"):
        releases = self.build_and_unpack()
        self.install(
            releases["gateway"], lambda _: self.edit("gateway", SHOP_REGION=region)
        )
        self.use_root(releases["login-service"])
        deploy.init_config("login-service")
        return releases

    def test_dev_inherits_shared_names_only(self):
        product = self.product()
        self.provide_credentials(product, common.BUILD / "dev")
        deploy.prepare()
        config = yaml.safe_load(
            (common.BUILD / "dev/login-service/config.yaml").read_text()
        )
        self.assertEqual(config["SHOP_REGION"], "eu")
        self.assertEqual(config["LOCAL_NOTE"], "login")

    def test_init_config_inherits_and_install_refuses_a_mismatch(self):
        self.product()
        releases = self.install_gateway_and_init_login()
        config = yaml.safe_load(
            (common.STATE / "login-service/config.yaml").read_text()
        )
        self.assertEqual(config["SHOP_REGION"], "nordic")
        self.assertEqual(config["LOCAL_NOTE"], "login")  # Unshared: its own value.
        self.edit("login-service", SHOP_REGION="eu")
        self.process.reset_mock()
        with self.assertRaises(common.DeployError) as raised:
            deploy.install()
        message = str(raised.exception)
        self.assertRegex(
            message,
            "SHOP_REGION in .*login-service/config.yaml must match "
            ".*gateway/config.yaml \\(gateway shares it\\)",
        )
        self.assertNotIn("nordic", message)
        self.assertNotIn("'eu'", message)
        self.assertEqual(self.commands(), [])
        # Unshared names may differ; the matching shared value installs.
        self.edit("login-service", SHOP_REGION="nordic", LOCAL_NOTE="different")
        self.use_root(releases["login-service"])
        deploy.install()
        self.assertTrue((common.STATE / "installed/login-service").is_file())

    def test_owner_must_define_what_it_shares(self):
        self.product()
        releases = self.build_and_unpack()
        with self.assertRaisesRegex(
            common.DeployError,
            "Missing SHOP_REGION in .*gateway/config.yaml; gateway shares it",
        ):
            self.install(
                releases["gateway"], lambda _: self.edit("gateway", SHOP_REGION=None)
            )

    def test_owner_upgrade_cannot_drop_a_share_its_dependents_take(self):
        self.product()
        self.install_gateway_and_init_login()
        self.edit("login-service", SHOP_REGION="nordic")
        deploy.install()
        before = (common.STATE / "metadata/gateway.json").read_bytes()
        shutil.rmtree(self.source)
        self.product(shares=(), version="1.0.1")
        release = self.build_and_unpack()["gateway"]
        self.use_root(release)
        self.process.reset_mock()
        with self.assertRaisesRegex(
            common.DeployError,
            "gateway no longer shares SHOP_REGION, which installed login-service "
            "take from it",
        ):
            deploy.install()
        self.assertEqual(self.commands(), [])
        self.assertEqual((common.STATE / "metadata/gateway.json").read_bytes(), before)


class ServiceChangeTests(ProductFixture):
    """Add and remove a service by editing bundles.yaml and components/ only."""

    def setUp(self):
        super().setUp()
        self.write_product(RENAMED)
        self.provide_credentials(RENAMED, common.BUILD / "dev")

    def catalog_entries(self):
        return yaml.safe_load((self.source / "bundles.yaml").read_text())["components"]

    def add_reports(self):
        entries = self.catalog_entries()
        entries["reports"] = REPORTS["catalog"]
        self.write_catalog(entries)
        self.write_component("reports", REPORTS)

    def remove_reports(self):
        entries = self.catalog_entries()
        del entries["reports"]
        self.write_catalog(entries)
        shutil.rmtree(str(self.source / "components/reports"))

    def dev_output(self):
        dev = common.BUILD / "dev"
        return (
            (common.BUILD / "install.yaml").read_text(),
            sorted(path.name for path in (dev / "routes").iterdir()),
        )

    def test_add_then_remove_in_dev_and_bundles(self):
        deploy.prepare()
        before, routes_before = self.dev_output()
        self.add_reports()
        for _ in range(2):  # Fresh and repeated prepare give the same product.
            deploy.prepare()
            text, routes = self.dev_output()
            self.assertIn("reports-web", text)
            self.assertIn("reports.conf", routes)
        bundle.build()
        current = (self.source / "dist/current-bundles.txt").read_text().split()
        self.assertIn("myproduct-reports-1.0.0-offline.tar.gz", current)

        self.remove_reports()
        for _ in range(2):
            deploy.prepare()
            self.assertEqual(self.dev_output(), (before, routes_before))
        self.assertNotIn("reports", (common.BUILD / "install.yaml").read_text())
        bundle.build()
        current = (self.source / "dist/current-bundles.txt").read_text().split()
        self.assertNotIn("myproduct-reports-1.0.0-offline.tar.gz", current)
        # The earlier archive is retained for a target that still runs reports.
        self.assertTrue(
            (self.source / "dist/myproduct-reports-1.0.0-offline.tar.gz").is_file()
        )
        self.assertFalse(
            (self.source / "build/bundle/myproduct-reports-1.0.0").exists()
        )

    def test_dangling_dependency_and_missing_directory_fail_before_writes(self):
        self.add_reports()
        deploy.prepare()
        output = common.BUILD / "install.yaml"
        before = output.read_bytes(), output.stat().st_mtime_ns
        self.remove_reports()
        entries = self.catalog_entries()
        entries["manual"]["requires"] = ["gateway", "reports"]
        self.write_catalog(entries)
        self.process.reset_mock()
        with self.assertRaisesRegex(
            common.DeployError, "components.manual.requires names reports"
        ):
            deploy.prepare()
        entries["manual"]["requires"] = ["gateway"]
        entries["reports"] = REPORTS["catalog"]
        self.write_catalog(entries)
        with self.assertRaisesRegex(
            common.DeployError, "Missing component directory .*reports"
        ):
            deploy.prepare()
        with self.assertRaisesRegex(common.DeployError, "Missing component directory"):
            bundle.build()
        self.assertEqual((output.read_bytes(), output.stat().st_mtime_ns), before)
        self.process.assert_not_called()

    def test_unselected_directory_is_never_read(self):
        """A stray directory, even with an invalid image, does not affect the product."""
        stray = copy.deepcopy(REPORTS)
        stray["manifests"] = [pod("stray-web", "not-qualified-image")]
        self.write_component("stray", stray)
        deploy.prepare()
        self.assertNotIn("stray", (common.BUILD / "install.yaml").read_text())
        self.assertFalse((common.BUILD / "dev/stray").exists())
        self.assertNotIn("not-qualified-image", bundle.manifest_images())
        bundle.build()
        self.assertNotIn(
            "stray", (self.source / "dist/current-bundles.txt").read_text()
        )

    def test_removed_source_keeps_installed_service_until_explicit_uninstall(self):
        self.add_reports()
        releases = self.build_and_unpack()
        self.provide_credentials(RENAMED, common.STATE)
        for name in ("gateway", "login-service", "orders", "reports"):
            self.install(releases[name])
        self.use_root(self.source)
        self.remove_reports()
        deploy.prepare()
        bundle.build()
        # A new source checkout never prunes installed production state.
        for path in (
            "installed/reports",
            "metadata/reports.json",
            "routes/reports.conf",
        ):
            self.assertTrue((common.STATE / path).is_file(), path)
        current = (self.source / "dist/current-bundles.txt").read_text().split()
        orders = [name for name in current if name.startswith("myproduct-orders-")]
        self.assertEqual(len(orders), 1)
        # Reinstalling a sibling from the new build keeps the reports registration.
        new_orders = self.root / "new-orders"
        new_orders.mkdir()
        path = self.source / "dist" / orders[0]
        # Built by this test; keep the Python 3.6 extract API.
        with tarfile.open(str(path)) as archive:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                archive.extractall(str(new_orders))
        (release,) = new_orders.iterdir()
        self.use_root(release)
        self.process.reset_mock()
        deploy.install()
        self.assertEqual(self.restarts(), ["orders"])
        self.assertTrue((common.STATE / "routes/reports.conf").is_file())
        # Explicit, scoped uninstall from the retained reports bundle.
        shutil.rmtree(self.source)
        self.use_root(releases["reports"])
        self.process.reset_mock()
        deploy.uninstall()
        self.assertEqual(self.restarts(), ["gateway"])
        self.assertFalse((common.STATE / "routes/reports.conf").exists())
        self.assertFalse((common.STATE / "installed/reports").exists())
        self.assertTrue((common.STATE / "installed/orders").is_file())
        self.assertTrue((common.STATE / "clients/orders/client.json").is_file())
