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

    def product(self, entries, files=()):
        """Write a catalog and a manifest directory for every listed component."""
        (self.root / "bundles.yaml").write_text(
            yaml.safe_dump(
                {"product": "myproduct", "components": entries}, sort_keys=False
            )
        )
        for name in entries if isinstance(entries, dict) else ():
            manifests = self.root / "components" / str(name) / "manifests"
            manifests.mkdir(parents=True, exist_ok=True)
            (manifests / "10.yaml").write_text(MANIFEST.replace("NAME", str(name)))
        for relative in files:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n")

    def refuse(self, pattern, entries, files=()):
        self.product(entries, files)
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

    def test_product_name_is_required_and_follows_user_name_rules(self):
        """It becomes the service user, unit prefix, network and archive name."""
        path = self.root / "bundles.yaml"
        self.product({"app": {}})
        self.assertEqual(catalog.product_name(self.root), "myproduct")
        self.assertEqual(
            catalog.source_descriptors(self.root)["app"]["product"], "myproduct"
        )
        path.write_text("components:\n  app: {}\n")
        with self.assertRaisesRegex(common.DeployError, "exactly product: <name>"):
            catalog.load_catalog(self.root)
        for name in ("hubbabubba", "my-shop", "a", "a" * 32):
            with self.subTest(name=name):
                path.write_text(
                    yaml.safe_dump({"product": name, "components": {"app": {}}})
                )
                self.assertEqual(catalog.product_name(self.root), name)
        for name in ("MyShop", "1shop", "shop-", "my_shop", "a" * 33, 7, None):
            with (
                self.subTest(name=name),
                self.assertRaisesRegex(common.DeployError, "invalid product name"),
            ):
                path.write_text(
                    yaml.safe_dump({"product": name, "components": {"app": {}}})
                )
                catalog.load_catalog(self.root)

    def test_shares_are_config_names_and_not_reserved(self):
        self.product({"gate": {"shares": ["SHOP_REGION", "PUBLIC_ORIGIN"]}})
        self.assertEqual(
            catalog.source_descriptors(self.root)["gate"]["shares"],
            ["SHOP_REGION", "PUBLIC_ORIGIN"],
        )
        for shares, pattern in (
            ("SHOP_REGION", "shares must be a list"),
            (["A", "A"], "shares must be a list without repeats"),
            (["shop_region"], "'shop_region' is not a config name"),
            (["SHOP-REGION"], "is not a config name"),
            ([7], "is not a config name"),
            (["PUBLIC_HOSTNAME"], "PUBLIC_HOSTNAME is reserved and cannot be shared"),
            (["SECRET_FILES"], "SECRET_FILES is reserved"),
            (["VOLUME_FILES"], "VOLUME_FILES is reserved"),
        ):
            with self.subTest(shares=shares):
                self.refuse(pattern, {"gate": {"shares": shares}})

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

    def test_unknown_fields_values_and_duplicate_keys_are_refused(self):
        self.refuse("allowed fields are", {"app": {"depends": ["x"]}})
        self.refuse("upgrade must be one of", {"app": {"upgrade": "sometimes"}})
        self.refuse("requires must be a list", {"app": {"requires": "x"}})
        self.refuse("components must be a nonempty map", {})
        (self.root / "bundles.yaml").write_text(
            "product: myproduct\ncomponents:\n  app: {}\n  app: {requires: []}\n"
        )
        with self.assertRaisesRegex(yaml.YAMLError, "duplicate key 'app'"):
            catalog.load_catalog(self.root)

    def test_dependency_errors_name_the_declaration(self):
        self.refuse(
            "components.app.requires names db, which is not in the catalog",
            {"app": {"requires": ["db"]}},
        )
        self.refuse("must not name itself", {"app": {"requires": ["app"]}})
        self.refuse(
            "Dependency cycle: a -> b -> a",
            {"a": {"requires": ["b"]}, "b": {"requires": ["a"]}},
        )

    def test_dependency_order_is_stable_for_unrelated_components(self):
        self.product(
            {
                "zeta": {},
                "app": {"requires": ["base"]},
                "base": {},
                "alpha": {},
            }
        )
        self.assertEqual(
            list(catalog.source_descriptors(self.root)),
            ["zeta", "base", "app", "alpha"],
        )

    def test_roles_need_a_declared_dependency_that_accepts_them(self):
        self.refuse(
            "routes: edge must also be listed in requires",
            {"edge": {"accepts": {"routes": "edge-routes"}}, "app": {"routes": "edge"}},
            ["components/app/route.conf"],
        )
        self.refuse(
            "app registers routes with edge, but edge does not accept routes",
            {"edge": {}, "app": {"requires": ["edge"], "routes": "edge"}},
            ["components/app/route.conf"],
        )
        self.refuse(
            "edge and edge2 both accept routes",
            {
                "edge": {"accepts": {"routes": "edge-routes"}},
                "edge2": {"accepts": {"routes": "edge2-routes"}},
            },
        )
        self.refuse(
            "clients needs public_from",
            {
                "login": {"accepts": {"clients": "login-clients"}},
                "app": {"requires": ["login"], "clients": "login"},
            },
            ["components/app/client.yaml"],
        )
        self.refuse(
            "accepts.routes must be a volume ID starting with edge-",
            {"edge": {"accepts": {"routes": "routes"}}},
        )

    def test_role_files_must_match_declarations(self):
        entries = {
            "edge": {"accepts": {"routes": "edge-routes"}},
            "app": {"requires": ["edge"], "routes": "edge"},
        }
        self.refuse("route.conf is missing for routes: edge", entries)
        self.refuse(
            "exists, so declare routes: <owner>",
            {
                "edge": {"accepts": {"routes": "edge-routes"}},
                "app": {"requires": ["edge"]},
            },
            ["components/app/route.conf"],
        )

    def test_selected_directories_and_version_files_are_confined(self):
        self.product({"app": {}})
        (self.root / "bundles.yaml").write_text(
            yaml.safe_dump(
                {"product": "myproduct", "components": {"app": {}, "gone": {}}}
            )
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
        os.symlink(str(outside / "VERSION"), str(self.root / "LINKED_VERSION"))
        for value, pattern in (
            ("../VERSION", "relative path inside"),
            ("/etc/hostname", "relative path inside"),
            ("LINKED_VERSION", "resolves outside"),
            ("MISSING_VERSION", "missing file"),
        ):
            with self.subTest(value=value):
                self.refuse(pattern, {"app": {"version_file": value}})
        (self.root / "BAD_VERSION").write_text("one\n")
        self.refuse(
            "must hold one major.minor.patch", {"app": {"version_file": "BAD_VERSION"}}
        )
        self.product({"app": {}})
        os.symlink(
            str(self.root / "components/app"), str(self.root / "components/alias")
        )
        self.refuse("Missing component directory", {"alias": {}})

    def test_compiled_descriptor_has_versions_and_ranges(self):
        (self.root / "BASE_VERSION").write_text("0.4.2\n")
        self.product(
            {
                "base": {"version_file": "BASE_VERSION", "upgrade": "newer-only"},
                "app": {"requires": ["base"]},
            }
        )
        descriptors = catalog.source_descriptors(self.root)
        self.assertEqual(
            descriptors["app"],
            {
                "name": "app",
                "product": "myproduct",
                "version": "1.0.0",
                "requires": {"base": {"min": "0.4.2", "before": "0.5.0"}},
                "upgrade": "always",
                "public_from": None,
                "shares": [],
                "routes": None,
                "clients": None,
                "accepts": {},
            },
        )
        for descriptor in descriptors.values():
            catalog.check_descriptor(descriptor, "fixture")
        # Bundles built before shares existed share nothing; still readable.
        older = {k: v for k, v in descriptors["app"].items() if k != "shares"}
        self.assertEqual(catalog.check_descriptor(older, "fixture")["shares"], [])
        self.assertNotIn("shares", older)
        for change, pattern in (
            ({"components": ["app"]}, "expected exactly the fields"),
            ({"version": "1.0"}, "three numeric parts"),
            ({"requires": {"base": {"min": "1.0.0", "before": "1.0.0"}}}, "Empty"),
            ({"name": "my_app"}, "invalid component ID"),
            ({"product": "My App"}, "invalid product name"),
            ({"shares": ["PUBLIC_HOSTNAME"]}, "reserved and cannot be shared"),
        ):
            failure = self.assertRaisesRegex(common.DeployError, pattern)
            with self.subTest(change=change), failure:
                catalog.check_descriptor(dict(descriptors["app"], **change), "fixture")

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
