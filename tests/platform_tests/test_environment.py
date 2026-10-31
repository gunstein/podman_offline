"""ENVIRONMENT in config.defaults.yaml: each container's environment (backlog 77)."""

import base64
import copy
import io
import shutil
from contextlib import redirect_stderr, redirect_stdout

import yaml
from deployment import common, deploy, validation

from helpers.product_fixture import ProductFixture, pod

SHOP = {
    "shop": {
        "defaults": {
            "DB_USER": "shop",
            "SECRET_FILES": {
                "shop-database-password": [
                    {"path": "credentials/database", "generate": ["value"]}
                ],
                "shop-tokens": [
                    {"path": "credentials/tokens", "generate": ["signing", "other"]}
                ],
            },
        },
        "manifests": [pod("shop-web", "localhost/shop:1", env={"FIXED": "1"})],
        "env": {
            "main": {
                "PORT": 5000,
                "Database__User": "@@DB_USER@@",
                "ConnectionStrings__Default": "Host=shop-db;Password=@@secret:shop-database-password/value@@",
                "Signing": "@@secret:shop-tokens/signing@@",
            }
        },
    }
}


def documents(path):
    return {
        (doc["kind"], doc["metadata"]["name"]): doc
        for doc in yaml.safe_load_all(path.read_text())
        if doc
    }


def decoded(secret):
    return {
        key: base64.b64decode(value).decode() for key, value in secret["data"].items()
    }


class EnvironmentTests(ProductFixture):
    def product(self, change=None):
        product = copy.deepcopy(SHOP)
        if change:
            change(product["shop"])
        if self.source.exists():
            shutil.rmtree(self.source)
        self.write_product(product)

    def test_environment_lowers_to_configmap_secret_and_env_from(self):
        self.product()
        deploy.prepare()
        rendered = documents(common.BUILD / "install.yaml")
        self.assertEqual(
            rendered[("ConfigMap", "shop-main-env")]["data"],
            {"PORT": "5000", "Database__User": "shop"},
        )
        dev = common.BUILD / "dev/shop"
        password = (dev / "credentials/database/value").read_text()
        signing = (dev / "credentials/tokens/signing").read_text()
        self.assertEqual(
            decoded(rendered[("Secret", "shop-main-env-secret")]),
            {
                "ConnectionStrings__Default": f"Host=shop-db;Password={password}",
                "Signing": signing,
            },
        )
        self.assertEqual(
            decoded(rendered[("Secret", "shop-database-password")]),
            {"value": password},
        )
        container = rendered[("Pod", "shop-web")]["spec"]["containers"][0]
        self.assertEqual(
            container["envFrom"],
            [
                {"configMapRef": {"name": "shop-main-env"}},
                {"secretRef": {"name": "shop-main-env-secret"}},
            ],
        )
        self.assertEqual(container["env"], [{"name": "FIXED", "value": "1"}])
        # Recipes live only in the transient effective config.
        written = yaml.safe_load((dev / "config.yaml").read_text())
        self.assertNotIn(common.SECRET_TEMPLATES, written)
        # Repeating prepare reuses the generated value.
        deploy.prepare()
        self.assertEqual((dev / "credentials/database/value").read_text(), password)

    def test_bundle_ships_environment_and_install_uses_it(self):
        self.product()
        releases = self.build_and_unpack()
        self.install(releases["shop"])
        installed = documents(common.QUADLET_DIR / "myproduct-shop.yaml")
        self.assertIn(("ConfigMap", "shop-main-env"), installed)
        self.assertIn(("Secret", "shop-main-env-secret"), installed)
        # The operator's config.yaml holds settings and secrets, never the
        # release's ENVIRONMENT or its recipes.
        written = yaml.safe_load((common.STATE / "shop/config.yaml").read_text())
        self.assertNotIn(common.SECRET_TEMPLATES, written)
        self.assertNotIn(common.ENVIRONMENT, written)
        self.assertEqual(written["DB_USER"], "shop")
        # ENVIRONMENT in the operator's config.yaml is refused with the reason.
        (common.STATE / "shop/config.yaml").write_text(
            yaml.safe_dump(dict(written, ENVIRONMENT={"main": {"A": "1"}}))
        )
        with self.assertRaisesRegex(
            common.DeployError, "ENVIRONMENT belongs only in the release's"
        ):
            self.install(releases["shop"])

    def test_validate_shows_each_container_without_values(self):
        self.product()
        stream = io.StringIO()
        with redirect_stdout(stream), redirect_stderr(stream):
            validation.validate()
        self.assertIn(
            "[OK] shop/main: ENVIRONMENT -> 2 settings (ConfigMap shop-main-env), "
            "2 secret (Secret shop-main-env-secret: shop-database-password, shop-tokens)",
            stream.getvalue(),
        )
        self.assertFalse(common.BUILD.exists())

    def test_declaration_errors_fail_before_any_write(self):
        def env(**values):
            return lambda shop: shop["env"]["main"].update(values)

        def replace_env(values):
            return lambda shop: shop.update(env={"main": values})

        def both(shop):
            shop["manifests"][0]["spec"]["containers"][0]["envFrom"] = [
                {"configMapRef": {"name": "shop-other"}}
            ]

        def recipe(shop):
            shop["defaults"]["SECRET_TEMPLATES"] = {"shop-other": {"A": "x"}}

        def same_name(shop):
            shop["defaults"]["SECRET_FILES"]["shop-main-env-secret"] = [
                {"path": "credentials/other", "generate": ["value"]}
            ]

        for label, change, pattern in (
            (
                "unknown container",
                lambda shop: shop.update(env={"web": {"A": "1"}}),
                "exactly one container named web; it has 0",
            ),
            (
                "hand-written envFrom",
                both,
                "use ENVIRONMENT or the container's hand-written envFrom",
            ),
            (
                "also in manifest env",
                env(fixed="2"),
                "fixed is also set in the manifest's env",
            ),
            ("colon key", env(**{"Logging:Level": "x"}), "use __ instead of :"),
            (
                "list value",
                env(Hosts=["a", "b"]),
                "Hosts must be one line of text, not a list or map",
            ),
            ("empty container", replace_env({}), "ENVIRONMENT.main must hold"),
            (
                "database variable",
                env(POSTGRES_PASSWORD_FILE="/x"),
                "keep it in the manifest's env",
            ),
            ("case duplicate", env(port=1), "PORT and port differ only in case"),
            (
                "undeclared secret",
                env(Other="@@secret:shop-databse-password/value@@"),
                (
                    "ENVIRONMENT.main: Other: SECRET_FILES has no shop-databse-password; "
                    "declared: shop-database-password, shop-tokens"
                ),
            ),
            (
                "unknown placeholder",
                env(Other="@@Secret:shop-tokens/signing@@"),
                "Other: unknown placeholder @@Secret:shop-tokens/signing@@",
            ),
            (
                "another component's secret",
                env(Other="@@secret:other-tokens/signing@@"),
                "other-tokens is another component's secret; shop may use only its own",
            ),
            ("unsafe public value", env(Note="a;b"), "unsafe substituted text"),
            ("written recipe", recipe, "SECRET_TEMPLATES is not supported"),
            (
                "name of a file source",
                same_name,
                "shop-main-env-secret .from ENVIRONMENT or MOUNTS. has the same name",
            ),
        ):
            with self.subTest(label):
                self.product(change)
                with self.assertRaisesRegex(common.DeployError, pattern):
                    deploy.prepare()
                self.assertFalse(common.BUILD.exists())

    def test_values_are_the_written_text(self):
        def raw(shop):
            del shop["env"]

        self.product(raw)
        defaults = self.source / "components/shop/config.defaults.yaml"
        settings = defaults.read_text()
        defaults.write_text(
            settings + "ENVIRONMENT:\n  main:\n"
            "    UMASK: 0022\n    ENABLED: yes\n    VERSION: 1.10\n"
            "    PORT: 5000\n    EMPTY:\n"
            "    DB: '@@secret:shop-database-password/value@@'\n"
            "    SIGNING: '@@secret:shop-tokens/signing@@'\n"
        )
        deploy.prepare()
        rendered = documents(common.BUILD / "install.yaml")
        self.assertEqual(
            rendered[("ConfigMap", "shop-main-env")]["data"],
            {
                "UMASK": "0022",
                "ENABLED": "yes",
                "VERSION": "1.10",
                "PORT": "5000",
                "EMPTY": "",
            },
        )
        defaults.write_text(
            settings + "ENVIRONMENT:\n  main:\n    URL: @@PUBLIC_ORIGIN@@\n"
        )
        with self.assertRaisesRegex(
            common.DeployError,
            "config.defaults.yaml at line [0-9]+: invalid YAML; write NAME: 'value' "
            "and quote "
            "values that start with @@",
        ):
            deploy.prepare()
