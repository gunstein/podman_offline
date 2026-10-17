"""A minimal worker, and adding or removing a service through YAML only."""

import copy
import shutil

import yaml
from product_fixture import RENAMED, WORKER, ProductFixture, pod, route

import bundle
from deployment import common, deploy

REPORTS = {
    "catalog": {"requires": ["gateway"], "routes": "gateway"},
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
            self.assertFalse((common.HOME / name).exists())
        self.process.reset_mock()
        deploy.uninstall(delete_data=True)
        self.assertEqual(self.restarts(), [])
        self.assertFalse((common.HOME / "installed/worker").exists())
        self.assertFalse((common.HOME / "metadata/worker.json").exists())


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
        self.provide_credentials(RENAMED, common.HOME)
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
            self.assertTrue((common.HOME / path).is_file(), path)
        current = (self.source / "dist/current-bundles.txt").read_text().split()
        orders = [name for name in current if name.startswith("myproduct-orders-")]
        self.assertEqual(len(orders), 1)
        # Reinstalling a sibling from the new build keeps the reports registration.
        self.use_root(releases["orders"])
        self.process.reset_mock()
        deploy.install()
        self.assertEqual(self.restarts(), ["orders"])
        # Explicit, scoped uninstall from the retained reports bundle.
        shutil.rmtree(self.source)
        self.use_root(releases["reports"])
        self.process.reset_mock()
        deploy.uninstall()
        self.assertEqual(self.restarts(), ["gateway"])
        self.assertFalse((common.HOME / "routes/reports.conf").exists())
        self.assertFalse((common.HOME / "installed/reports").exists())
        self.assertTrue((common.HOME / "installed/orders").is_file())
        self.assertTrue((common.HOME / "clients/orders/client.json").is_file())
