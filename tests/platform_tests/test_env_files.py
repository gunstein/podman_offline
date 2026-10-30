"""env/<container>.yaml and the short secret declaration/reference (backlog 77)."""

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
        "catalog": {},
        "defaults": {
            "DB_USER": "shop",
            "SECRET_FILES": {
                "shop-database-password": "generate",
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
                "ConnectionStrings__Default": "Host=shop-db;Password=@@secret:shop-database-password@@",
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


class EnvFileTests(ProductFixture):
    def product(self, change=None):
        product = copy.deepcopy(SHOP)
        if change:
            change(product["shop"])
        if self.source.exists():
            shutil.rmtree(self.source)
        self.write_product(product)

    def test_env_file_lowers_to_configmap_secret_and_env_from(self):
        self.product()
        deploy.prepare()
        rendered = documents(common.BUILD / "install.yaml")
        self.assertEqual(
            rendered[("ConfigMap", "shop-main-env")]["data"],
            {"PORT": "5000", "Database__User": "shop"},
        )
        dev = common.BUILD / "dev/shop"
        password = (dev / "credentials/shop-database-password/value").read_text()
        signing = (dev / "credentials/tokens/signing").read_text()
        self.assertEqual(
            decoded(rendered[("Secret", "shop-main-env-secret")]),
            {
                "ConnectionStrings__Default": f"Host=shop-db;Password={password}",
                "Signing": signing,
            },
        )
        # The short declaration is an ordinary generated Secret with key value.
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
        self.assertEqual(
            (dev / "credentials/shop-database-password/value").read_text(), password
        )

    def test_bundle_ships_env_and_install_uses_it(self):
        self.product()
        releases = self.build_and_unpack()
        self.assertTrue((releases["shop"] / "components/shop/env/main.yaml").is_file())
        self.assertIn(
            "components/shop/env/main.yaml",
            (releases["shop"] / "checksums.sha256").read_text(),
        )
        self.install(releases["shop"])
        installed = documents(common.QUADLET_DIR / "myproduct-shop.yaml")
        self.assertIn(("ConfigMap", "shop-main-env"), installed)
        self.assertIn(("Secret", "shop-main-env-secret"), installed)
        written = yaml.safe_load((common.STATE / "shop/config.yaml").read_text())
        self.assertNotIn(common.SECRET_TEMPLATES, written)

    def test_validate_shows_each_env_file_without_values(self):
        self.product()
        stream = io.StringIO()
        with redirect_stdout(stream), redirect_stderr(stream):
            validation.validate()
        self.assertIn(
            "[OK] shop/main: env/main.yaml -> 2 settings (ConfigMap shop-main-env), "
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
            shop["defaults"]["SECRET_TEMPLATES"] = {"shop-main-env-secret": {"A": "x"}}

        for label, change, pattern in (
            (
                "unknown container",
                lambda shop: shop.update(env={"web": {"A": "1"}}),
                "exactly one container named web; it has 0",
            ),
            ("hand-written envFrom", both, "use env/main.yaml or keep the container's"),
            (
                "also in manifest env",
                env(fixed="2"),
                "fixed is also set in the manifest's env",
            ),
            ("colon key", env(**{"Logging:Level": "x"}), "use __ instead of :"),
            (
                "boolean",
                env(Enabled=True),
                "Enabled must be text or an integer; quote it",
            ),
            ("empty file", replace_env({}), "is empty"),
            (
                "database variable",
                env(POSTGRES_PASSWORD_FILE="/x"),
                "keep it in the manifest's env",
            ),
            ("case duplicate", env(port=1), "PORT and port differ only in case"),
            (
                "short ref to multi-key",
                env(Other="@@secret:shop-tokens@@"),
                "needs SECRET_FILES.shop-tokens declared as",
            ),
            (
                "short ref undeclared",
                env(Other="@@secret:shop-missing@@"),
                "needs SECRET_FILES.shop-missing",
            ),
            ("unsafe public value", env(Note="a;b"), "unsafe substituted text"),
            (
                "recipe collision",
                recipe,
                "SECRET_TEMPLATES.shop-main-env-secret is the Secret",
            ),
            (
                "wrong short declaration",
                lambda shop: shop["defaults"]["SECRET_FILES"].update(
                    {"shop-x": "make"}
                ),
                "write 'shop-x: generate'",
            ),
        ):
            with self.subTest(label):
                self.product(change)
                with self.assertRaisesRegex(common.DeployError, pattern):
                    deploy.prepare()
                self.assertFalse(common.BUILD.exists())
        self.product()
        (self.source / "components/shop/env/notes.txt").write_text("x\n")
        with self.assertRaisesRegex(common.DeployError, "holds only <container>.yaml"):
            deploy.prepare()

    def test_client_variables_stay_in_the_manifest(self):
        def client(shop):
            shop["client"] = {
                "id": "shop",
                "base_path": "/shop",
                "scopes": ["openid", "profile", "shop"],
                "certificate": "credentials/client/client.crt",
                "environment": {"id": "APP_ID", "base_path": "BASE_PATH"},
            }
            shop["env"]["main"]["APP_ID"] = "shop"

        product = copy.deepcopy(SHOP)
        client(product["shop"])
        product["shop"]["route"] = "location /shop/ { return 204; }\n"
        product["edge"] = {
            "role": "gateway",
            "catalog": {},
            "manifests": [pod("edge-proxy", "localhost/edge:1", ["pvc:edge-routes"])],
            "defaults": {"PUBLIC_ORIGIN": "https://shop.test", "HTTPS_PORT": 443},
        }
        product["login"] = {
            "role": "identity",
            "catalog": {},
            "manifests": [
                pod("login-server", "localhost/login:1", ["pvc:login-clients"])
            ],
        }
        self.write_product(product)
        with self.assertRaisesRegex(
            common.DeployError, "APP_ID is compared with client.yaml; keep it"
        ):
            deploy.prepare()

    def test_short_reference_refuses_extra_retained_files(self):
        self.product()
        deploy.prepare()
        extra = common.BUILD / "dev/shop/credentials/shop-database-password/old"
        extra.write_text("stale")
        with self.assertRaisesRegex(
            common.DeployError,
            "SECRET_FILES.shop-database-password must deliver exactly the file value",
        ):
            deploy.prepare()
