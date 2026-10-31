"""MOUNTS in config.defaults.yaml: release files mounted into containers (backlog 77)."""

import base64
import copy
import io
import shutil
from contextlib import redirect_stderr, redirect_stdout

import yaml
from deployment import common, deploy, validation

from helpers.product_fixture import ProductFixture, pod

ROLES_SQL = (
    "-- Filled in at install.\n"
    "ALTER ROLE @@DB_USER@@ PASSWORD '@@secret:shop-database-password/value@@';\n"
)

SHOP = {
    "shop": {
        "defaults": {
            "DB_USER": "shop",
            "SECRET_FILES": {
                "shop-database-password": [
                    {"path": "credentials/database", "generate": ["value"]}
                ],
            },
        },
        "manifests": [
            pod(
                "shop-web",
                "localhost/shop:1",
                volumes=["secret:shop-database-password"],
            )
        ],
        "mounts": {"main": {"/sql/10-roles.sql": "sql/10-roles.sql"}},
        "files": {"sql/10-roles.sql": ROLES_SQL, "sql/notes.txt": "plain\n"},
    }
}


def documents(path):
    return {
        (doc["kind"], doc["metadata"]["name"]): doc
        for doc in yaml.safe_load_all(path.read_text())
        if doc
    }


class MountsTests(ProductFixture):
    def product(self, change=None):
        product = copy.deepcopy(SHOP)
        if change:
            change(product["shop"])
        if self.source.exists():
            shutil.rmtree(self.source)
        self.write_product(product)

    def test_file_is_rendered_into_a_secret_and_mounted_read_only(self):
        self.product(
            lambda shop: shop["mounts"]["main"].update(
                {"/etc/notes.txt": "sql/notes.txt"}
            )
        )
        deploy.prepare()
        rendered = documents(common.BUILD / "install.yaml")
        password = (common.BUILD / "dev/shop/credentials/database/value").read_text()
        secret = rendered[("Secret", "shop-main-files")]
        self.assertEqual(
            {
                key: base64.b64decode(value).decode()
                for key, value in secret["data"].items()
            },
            {
                "10-roles.sql": "-- Filled in at install.\n"
                f"ALTER ROLE shop PASSWORD '{password}';\n",
                "notes.txt": "plain\n",
            },
        )
        spec = rendered[("Pod", "shop-web")]["spec"]
        self.assertEqual(
            spec["containers"][0]["volumeMounts"][1:],
            [
                {
                    "name": "main-files",
                    "mountPath": "/sql/10-roles.sql",
                    "subPath": "10-roles.sql",
                    "readOnly": True,
                },
                {
                    "name": "main-files",
                    "mountPath": "/etc/notes.txt",
                    "subPath": "notes.txt",
                    "readOnly": True,
                },
            ],
        )
        self.assertEqual(
            spec["volumes"][-1],
            {
                "name": "main-files",
                "secret": {
                    "secretName": "shop-main-files",
                    "items": [
                        {"key": "10-roles.sql", "path": "10-roles.sql"},
                        {"key": "notes.txt", "path": "notes.txt"},
                    ],
                },
            },
        )
        written = yaml.safe_load((common.BUILD / "dev/shop/config.yaml").read_text())
        self.assertNotIn(common.MOUNTS, written)
        self.assertNotIn(common.SECRET_TEMPLATES, written)

    def test_bundle_ships_files_and_install_uses_them(self):
        self.product()
        releases = self.build_and_unpack()
        self.assertTrue(
            (releases["shop"] / "components/shop/files/sql/10-roles.sql").is_file()
        )
        self.install(releases["shop"])
        installed = documents(common.QUADLET_DIR / "myproduct-shop.yaml")
        self.assertIn(("Secret", "shop-main-files"), installed)
        written = yaml.safe_load((common.STATE / "shop/config.yaml").read_text())
        self.assertNotIn(common.MOUNTS, written)
        (common.STATE / "shop/config.yaml").write_text(
            yaml.safe_dump(dict(written, MOUNTS={"main": {"/a": "a"}}))
        )
        with self.assertRaisesRegex(
            common.DeployError, "MOUNTS belongs only in the release's"
        ):
            self.install(releases["shop"])

    def test_validate_names_paths_and_secrets_without_values(self):
        self.product()
        stream = io.StringIO()
        with redirect_stdout(stream), redirect_stderr(stream):
            validation.validate()
        self.assertIn(
            "[OK] shop/main: MOUNTS -> /sql/10-roles.sql "
            "(Secret shop-main-files: shop-database-password)",
            stream.getvalue(),
        )
        self.assertFalse(common.BUILD.exists())

    def test_declaration_errors_fail_before_any_write(self):
        def mounts(value):
            return lambda shop: shop.update(mounts={"main": value})

        def sql(text):
            return lambda shop: shop["files"].update({"sql/10-roles.sql": text})

        def volume(shop):
            shop["manifests"][0]["spec"]["volumes"].append(
                {"name": "main-files", "emptyDir": {}}
            )

        for label, change, pattern in (
            (
                "unknown container",
                lambda shop: shop.update(mounts={"web": {"/a.sql": "sql/notes.txt"}}),
                "exactly one container named web; it has 0",
            ),
            (
                "relative target",
                mounts({"sql/a.sql": "sql/notes.txt"}),
                "is not an absolute path",
            ),
            (
                "dotted target",
                mounts({"/sql/../a.sql": "sql/notes.txt"}),
                "is not an absolute path",
            ),
            (
                "outside files",
                mounts({"/a.sql": "../VERSION"}),
                "write a file under components/shop/files/",
            ),
            (
                "missing file",
                mounts({"/a.sql": "sql/missing.sql"}),
                "files/sql/missing.sql is missing",
            ),
            ("empty", mounts({}), "MOUNTS.main must hold"),
            (
                "undeclared secret",
                sql("'@@secret:shop-databse-password/value@@'"),
                "SECRET_FILES has no shop-databse-password; declared: shop-database-password",
            ),
            (
                "another component's secret",
                sql("'@@secret:other-tokens/value@@'"),
                "uses other-tokens, another component's secret",
            ),
            (
                "unknown setting",
                sql("@@DB_USR@@"),
                "uses @@DB_USR@@, which is not a setting",
            ),
            ("malformed", sql("@@secret:x@@"), "unknown or nested placeholder"),
            ("volume name taken", volume, "already has a volume named main-files"),
            (
                "mount path taken",
                mounts({"/mnt/shop-database-password": "sql/notes.txt"}),
                "is also a volumeMount in the manifest",
            ),
        ):
            with self.subTest(label):
                self.product(change)
                with self.assertRaisesRegex(common.DeployError, pattern):
                    deploy.prepare()
                self.assertFalse(common.BUILD.exists())
