"""Catalog, descriptor and installed-metadata validation before any side effect."""

import json
import os
import tempfile
import unittest
from pathlib import Path

import yaml
from deployment import catalog, common

MANIFEST = "kind: Pod\nmetadata: {name: NAME-pod}\n"


class CatalogTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "VERSION").write_text("1.0.0\n")

    def product(self, names, files=(), **roles):
        """Write a catalog and a manifest directory for every listed component.

        roles are the optional top-level gateway and identity names.
        """
        document = dict({"product": "myproduct"}, **roles)
        document["components"] = list(names)
        (self.root / "bundles.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False)
        )
        for name in names:
            manifests = self.root / "components" / str(name) / "manifests"
            manifests.mkdir(parents=True, exist_ok=True)
            (manifests / "10.yaml").write_text(MANIFEST.replace("NAME", str(name)))
            version = manifests.parent / "VERSION"
            if not version.exists():
                version.write_text("1.0.0\n")
        for relative in files:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n")

    def refuse(self, pattern, names, files=(), **roles):
        self.product(names, files, **roles)
        with self.assertRaisesRegex(common.DeployError, pattern):
            catalog.source_descriptors(self.root)

    def test_component_ids_follow_resource_name_rules_without_rewriting(self):
        self.product({"my-identity": {}})
        self.assertEqual(list(catalog.source_descriptors(self.root)), ["my-identity"])
        for name in ("my_identity", "Gateway", "-edge", "edge-", "a.b"):
            with self.subTest(name=name):
                self.refuse(
                    "invalid component ID.*my-identity \\(not my_identity\\)",
                    {name: {}},
                )
        self.refuse("reserved for shared state", {"metadata": {}})

    def test_component_versions_are_independent_and_need_no_root_version(self):
        self.product({"worker": {}, "manual": {}})
        (self.root / "VERSION").unlink()
        (self.root / "components/worker/VERSION").write_text("2.3.4\n")
        descriptors = catalog.source_descriptors(self.root)
        self.assertEqual(descriptors["worker"]["version"], "2.3.4")
        self.assertEqual(descriptors["manual"]["version"], "1.0.0")
        (self.root / "components/manual/VERSION").write_bytes(b"\xff")
        with self.assertRaisesRegex(
            common.DeployError, "components/manual/VERSION.*must hold"
        ):
            catalog.source_descriptors(self.root)

    def test_product_name_is_required_and_follows_user_name_rules(self):
        """It becomes the service user, unit prefix, network and archive name."""
        path = self.root / "bundles.yaml"
        self.product({"app": {}})
        self.assertEqual(catalog.product_name(self.root), "myproduct")
        self.assertEqual(
            catalog.source_descriptors(self.root)["app"]["product"], "myproduct"
        )
        path.write_text("components: [app]\n")
        with self.assertRaisesRegex(common.DeployError, "must contain product: <name>"):
            catalog.load_catalog(self.root)
        for name in ("hubbabubba", "my-shop", "a", "a" * 32):
            with self.subTest(name=name):
                path.write_text(
                    yaml.safe_dump({"product": name, "components": ["app"]})
                )
                self.assertEqual(catalog.product_name(self.root), name)
        for name in ("MyShop", "1shop", "shop-", "my_shop", "a" * 33, 7, None):
            with self.subTest(name=name):
                with self.assertRaisesRegex(common.DeployError, "invalid product name"):
                    path.write_text(
                        yaml.safe_dump({"product": name, "components": ["app"]})
                    )
                    catalog.load_catalog(self.root)

    def test_ids_that_extend_another_id_are_refused(self):
        """orders-data-db would be a resource name of both orders and orders-data."""
        self.refuse(
            "component orders-data starts with orders-.*rename one",
            {"orders": {}, "orders-data": {}},
        )
        self.product({"orders": {}, "ordersdata": {}, "data-orders": {}})
        self.assertEqual(
            sorted(catalog.source_descriptors(self.root)),
            ["data-orders", "orders", "ordersdata"],
        )

    def test_components_is_a_plain_list_of_ids(self):
        path = self.root / "bundles.yaml"
        self.product({"app": {}})
        path.write_text("product: myproduct\ncomponents:\n  app:\n    requires: [db]\n")
        with self.assertRaisesRegex(
            common.DeployError, "components is a list of component IDs"
        ):
            catalog.load_catalog(self.root)
        self.refuse("components must be a nonempty list", [])
        self.refuse("components lists an ID twice", ["app", "app"])

    def test_dependency_order_puts_the_gateway_first_then_the_list(self):
        self.product(["zeta", "app", "base", "alpha"], gateway="base")
        self.assertEqual(
            list(catalog.source_descriptors(self.root)),
            ["base", "zeta", "app", "alpha"],
        )

    def test_gateway_and_identity_derive_the_explicit_entries(self):
        """The normalized entries equal what the earlier explicit fields said."""
        self.product(
            {
                "edge": {},
                "login": {},
                "shop": {},
                "worker": {},
            },
            [
                "components/login/route.conf",
                "components/shop/route.conf",
                "components/shop/client.yaml",
            ],
            gateway="edge",
            identity="login",
        )
        entries = catalog.load_catalog(self.root)

        def entry(**fields):
            return dict(
                {
                    "requires": [],
                    "public_from": "edge",
                    "routes": None,
                    "clients": None,
                    "apis": None,
                    "accepts": {},
                    "api_secrets": {},
                },
                **fields,
            )

        self.assertEqual(
            entries,
            {
                "edge": entry(
                    public_from=None,
                    accepts={"routes": "edge-routes"},
                ),
                "login": entry(
                    requires=["edge"],
                    routes="edge",
                    accepts={"clients": "login-clients"},
                ),
                "shop": entry(
                    requires=["edge", "login"], routes="edge", clients="login"
                ),
                # No registration file: no link to identity.
                "worker": entry(requires=["edge"]),
            },
        )
        self.assertEqual(
            catalog.derived_lines(entries),
            [
                "edge: receives routes in edge-routes",
                (
                    "login: receives clients in login-clients; public settings and "
                    "routes from edge; requires edge"
                ),
                (
                    "shop: public settings and routes from edge; client.yaml -> login; "
                    "requires edge, login"
                ),
                "worker: public settings from edge; requires edge",
            ],
        )
        # Identity accepts clients only while some component has client.yaml.
        (self.root / "components/shop/client.yaml").unlink()
        self.assertEqual(catalog.load_catalog(self.root)["login"]["accepts"], {})
        # Without a gateway nothing takes public settings (a worker-only product).
        self.product({"worker": {}, "other": {}})
        self.assertEqual(
            {
                name: e["public_from"]
                for name, e in catalog.load_catalog(self.root).items()
            },
            {"worker": None, "other": None},
        )

    def test_catalog_refusals_name_the_file_and_the_rule(self):
        apps = {"edge": {}, "login": {}, "shop": {}}
        both = {"gateway": "edge", "identity": "login"}
        for label, entries, files, roles, pattern in (
            (
                "unlisted gateway",
                apps,
                (),
                {"gateway": "proxy"},
                "gateway: 'proxy' must be one of the listed components",
            ),
            (
                "unlisted identity",
                apps,
                (),
                {"identity": "auth"},
                "identity: 'auth' must be one of the listed components",
            ),
            (
                "route without gateway",
                apps,
                ["components/shop/route.conf"],
                {},
                "components/shop/route.conf needs a gateway",
            ),
            (
                "route on the gateway",
                apps,
                ["components/edge/route.conf"],
                both,
                "the gateway serves routes itself",
            ),
            (
                "client without identity",
                apps,
                ["components/shop/client.yaml"],
                {"gateway": "edge"},
                "client.yaml needs identity: <id>",
            ),
            (
                "client without gateway",
                apps,
                ["components/shop/client.yaml"],
                {"identity": "login"},
                "needs the gateway's public origin",
            ),
            (
                "client on identity",
                apps,
                ["components/login/client.yaml"],
                both,
                "identity does not register a client with itself",
            ),
        ):
            with self.subTest(label):
                __import__("shutil").rmtree(str(self.root / "components"), True)
                self.refuse(pattern, entries, files, **roles)
        (self.root / "bundles.yaml").write_text(
            "product: myproduct\nproxy: edge\ncomponents: [edge]\n"
        )
        with self.assertRaisesRegex(common.DeployError, "optionally gateway"):
            catalog.load_catalog(self.root)

    def test_selected_directories_and_version_files_are_confined(self):
        self.product({"app": {}})
        (self.root / "bundles.yaml").write_text(
            yaml.safe_dump({"product": "myproduct", "components": ["app", "gone"]})
        )
        with self.assertRaisesRegex(
            common.DeployError,
            "Missing component directory .*gone for catalog entry gone",
        ):
            catalog.source_descriptors(self.root)
        outside = self.root.parent / (self.root.name + "-outside")
        outside.mkdir()
        self.addCleanup(lambda: __import__("shutil").rmtree(str(outside)))
        (outside / "VERSION").write_text("9.9.9\n")
        version = self.root / "components/app/VERSION"
        version.unlink()
        os.symlink(str(outside / "VERSION"), str(version))
        with self.assertRaisesRegex(common.DeployError, "resolves outside"):
            catalog.source_descriptors(self.root)
        version.unlink()
        with self.assertRaisesRegex(
            common.DeployError, "missing file.*components/app/VERSION"
        ):
            catalog.source_descriptors(self.root)
        version.write_text("one\n")
        with self.assertRaisesRegex(
            common.DeployError, "components/app/VERSION.*must hold"
        ):
            catalog.source_descriptors(self.root)
        version.write_text("1.0.0\n")
        self.product({"app": {}})
        os.symlink(
            str(self.root / "components/app"), str(self.root / "components/alias")
        )
        self.refuse("Missing component directory", {"alias": {}})

    def test_compiled_descriptor_has_versions_and_ranges(self):
        self.product(["base", "app"], gateway="base")
        (self.root / "components/base/VERSION").write_text("0.4.2\n")
        descriptors = catalog.source_descriptors(self.root)
        self.assertEqual(
            descriptors["app"],
            {
                "name": "app",
                "product": "myproduct",
                "version": "1.0.0",
                "requires": {"base": {"min": "0.4.2", "before": "0.5.0"}},
                "public_from": "base",
                "routes": None,
                "clients": None,
                "apis": None,
                "accepts": {},
                "api_secrets": {},
            },
        )
        for descriptor in descriptors.values():
            document = catalog.descriptor_document(descriptor)
            # Written files keep the fields older releases read; reading drops them.
            self.assertEqual((document["upgrade"], document["shares"]), ("always", []))
            self.assertEqual(catalog.check_descriptor(document, "fixture"), descriptor)
        # Bundles built before apis existed register no API; still readable, and
        # an older release's upgrade and shares values are ignored.
        older = dict(
            {k: v for k, v in descriptors["app"].items() if k != "apis"},
            upgrade="newer-only",
            shares=["SHOP_REGION"],
        )
        self.assertEqual(catalog.check_descriptor(older, "fixture"), descriptors["app"])
        for change, pattern in (
            ({"components": ["app"]}, "expected exactly the fields"),
            ({"version": "1.0"}, "three numeric parts"),
            ({"requires": {"base": {"min": "1.0.0", "before": "1.0.0"}}}, "Empty"),
            ({"name": "my_app"}, "invalid component ID"),
            ({"product": "My App"}, "invalid product name"),
        ):
            failure = self.assertRaisesRegex(common.DeployError, pattern)
            with self.subTest(change=change):
                with failure:
                    catalog.check_descriptor(
                        dict(descriptors["app"], **change), "fixture"
                    )

    def test_metadata_from_before_product_names_is_named_not_corrupt(self):
        """0.4.10 metadata has no product; say so instead of 'invalid'."""
        home = self.root / "home"
        (home / "metadata").mkdir(parents=True)
        old = {
            "name": "app",
            "version": "1.0.0",
            "requires": {},
            "upgrade": "always",
            "public_from": None,
            "routes": None,
            "clients": None,
            "accepts": {},
        }
        (home / "metadata/app.json").write_text(json.dumps(old))
        with self.assertRaisesRegex(
            common.DeployError,
            "app.json was written by a release before product names.*no migration",
        ):
            catalog.load_installed_metadata(home)
        (home / "metadata/app.json").write_text(json.dumps(dict(old, extra=1)))
        with self.assertRaisesRegex(common.DeployError, "Invalid installed metadata"):
            catalog.load_installed_metadata(home)

    def test_installed_metadata_is_read_strictly(self):
        home = self.root / "home"
        (home / "installed").mkdir(parents=True)
        (home / "metadata").mkdir()
        (home / "installed/app").write_text("1.0.0\n")
        with self.assertRaisesRegex(common.DeployError, "Missing installed metadata"):
            catalog.dependents({}, home, "base")
        (home / "installed/.install-temporary").write_text("partial")
        (home / "metadata/.install-temporary").write_text("partial")
        descriptor = {
            "name": "app",
            "product": "myproduct",
            "version": "1.0.0",
            "requires": {"base": {"min": "1.0.0", "before": "2.0.0"}},
            "upgrade": "always",
            "public_from": None,
            "routes": None,
            "clients": None,
            "accepts": {},
        }
        (home / "metadata/app.json").write_text(json.dumps(descriptor))
        installed = catalog.load_installed_metadata(home)
        self.assertEqual(catalog.dependents(installed, home, "base"), ["app"])
        (home / "metadata/other.json").write_text(json.dumps(descriptor))
        with self.assertRaisesRegex(common.DeployError, "Invalid installed metadata"):
            catalog.load_installed_metadata(home)


if __name__ == "__main__":
    unittest.main()
