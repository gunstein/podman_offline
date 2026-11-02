"""MOUNTS in config.defaults.yaml: release files mounted into containers (backlog 77)."""

import base64
import copy
import io
import os
import shutil
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from unittest import mock

import bundle
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

    def test_links_out_of_files_are_refused_in_validate_prepare_and_bundle(self):
        """A linked directory under files/ must not pull in a file from elsewhere."""
        self.product(
            lambda shop: shop["mounts"]["main"].update(
                {"/etc/input.txt": "linked/input.txt"}
            )
        )
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "input.txt").write_text("PRIVATE-OUTSIDE-FILE\n")
        files = self.source / "components/shop/files"
        (files / "linked").symlink_to(outside, target_is_directory=True)
        for operation in (validation.validate, deploy.prepare):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(
                    common.DeployError, "Refuse symlink in component file path"
                ):
                    operation()
        self.assertFalse(common.BUILD.exists())
        # An unreferenced link under files/ is not copied into a bundle either.
        self.product()
        (self.source / "components/shop/files/linked").symlink_to(
            outside, target_is_directory=True
        )
        with self.assertRaisesRegex(bundle.BundleError, "without symlinks"):
            self.build_and_unpack()

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


# Backlog 80: a declared secret file mounted directly, beside a rendered file.
CA = b"-----BEGIN CERTIFICATE-----\nY2E=\n-----END CERTIFICATE-----\n"
ROOT = b"-----BEGIN CERTIFICATE-----\ncm9vdA==\n-----END CERTIFICATE-----\n\n"
# Not text: a NUL, invalid UTF-8, a placeholder and no final newline.
PFX = b"\x30\x82\x00\xff@@NOT_A_SETTING@@\xfe\x00"

TRUST = {
    "shop": {
        "defaults": {
            "DB_USER": "shop",
            "SECRET_FILES": {
                "shop-database-password": [
                    {"path": "credentials/database", "generate": ["value"]}
                ],
                "shop-trust-chain": [{"path": "credentials/trust"}],
            },
        },
        "manifests": [
            pod(
                "shop-web",
                "localhost/shop:1",
                volumes=["secret:shop-database-password"],
                initContainers=[
                    {
                        "name": "migrate",
                        "image": "localhost/shop:1",
                        "imagePullPolicy": "Never",
                    }
                ],
            )
        ],
        "mounts": {
            "main": {
                "/sql/10-roles.sql": "sql/10-roles.sql",
                "/run/secrets/trust/root.crt": "@@secret:shop-trust-chain/root.crt@@",
                "/run/secrets/trust/ca.crt": "@@secret:shop-trust-chain/ca.crt@@",
                "/etc/ssl/certs/shop-ca.pem": "@@secret:shop-trust-chain/ca.crt@@",
            },
            "migrate": {
                "/run/certificates/signing.pfx": "@@secret:shop-trust-chain/signing.pfx@@",
            },
        },
        "files": {"sql/10-roles.sql": ROLES_SQL},
    }
}

# What the platform must add, written out in full (not computed by mounts.py).
TRUST_VOLUME = {
    "name": "shop-trust-chain-mount",
    "secret": {
        "secretName": "shop-trust-chain",
        "items": [
            {"key": "root.crt", "path": "root.crt"},
            {"key": "ca.crt", "path": "ca.crt"},
            {"key": "signing.pfx", "path": "signing.pfx"},
        ],
    },
}


def trust_mount(target, key):
    return {
        "name": "shop-trust-chain-mount",
        "mountPath": target,
        "subPath": key,
        "readOnly": True,
    }


class SecretFileMountTests(ProductFixture):
    def tree(self, directory):
        """Every file below directory with its bytes, to prove nothing was written."""
        return {
            str(path.relative_to(directory)): path.read_bytes()
            for path in sorted(directory.rglob("*"))
            if path.is_file()
        }

    def product(self, change=None):
        product = copy.deepcopy(TRUST)
        if change:
            change(product["shop"])
        if self.source.exists():
            shutil.rmtree(self.source)
        self.write_product(product)

    def deliver(self, directory):
        """The trust chain's files, as an operator or dev script provides them."""
        trust = directory / "credentials/trust"
        trust.mkdir(parents=True, exist_ok=True)
        for name, data in (("root.crt", ROOT), ("ca.crt", CA), ("signing.pfx", PFX)):
            (trust / name).write_bytes(data)

    def test_secret_files_are_mounted_from_their_own_secret_beside_a_rendered_file(
        self,
    ):
        self.product()
        self.deliver(common.BUILD / "dev/shop")
        deploy.prepare()
        rendered = documents(common.BUILD / "install.yaml")
        spec = rendered[("Pod", "shop-web")]["spec"]
        main = spec["containers"][0]
        self.assertEqual(
            main["volumeMounts"][1:],
            [
                {
                    "name": "main-files",
                    "mountPath": "/sql/10-roles.sql",
                    "subPath": "10-roles.sql",
                    "readOnly": True,
                },
                trust_mount("/run/secrets/trust/root.crt", "root.crt"),
                trust_mount("/run/secrets/trust/ca.crt", "ca.crt"),
                trust_mount("/etc/ssl/certs/shop-ca.pem", "ca.crt"),
            ],
        )
        self.assertEqual(
            spec["initContainers"][0]["volumeMounts"],
            [trust_mount("/run/certificates/signing.pfx", "signing.pfx")],
        )
        # One volume for the Secret in the Pod, shared by both containers.
        self.assertEqual(
            [v for v in spec["volumes"] if v["name"] == "shop-trust-chain-mount"],
            [TRUST_VOLUME],
        )
        # The rendered file still has its own Secret; the trust chain is not copied.
        files = rendered[("Secret", "shop-main-files")]["data"]
        self.assertEqual(sorted(files), ["10-roles.sql"])
        secrets = [name for kind, name in rendered if kind == "Secret"]
        self.assertEqual(secrets.count("shop-trust-chain"), 1)
        self.assertNotIn("shop-migrate-files", secrets)
        # Byte for byte: no substitution, decoding or trimming.
        data = rendered[("Secret", "shop-trust-chain")]["data"]
        self.assertEqual(
            {key: base64.b64decode(value) for key, value in data.items()},
            {"root.crt": ROOT, "ca.crt": CA, "signing.pfx": PFX},
        )

    def test_install_from_a_bundle_again_and_uninstall(self):
        self.product()
        releases = self.build_and_unpack()
        bundled = releases["shop"] / "components/shop/config.defaults.yaml"
        self.assertIn("@@secret:shop-trust-chain/ca.crt@@", bundled.read_text())
        for attempt in ("first", "same version again"):
            with self.subTest(attempt=attempt):
                self.install(releases["shop"], self.deliver)
                installed = documents(common.QUADLET_DIR / "myproduct-shop.yaml")
                spec = installed[("Pod", "shop-web")]["spec"]
                self.assertIn(TRUST_VOLUME, spec["volumes"])
                data = installed[("Secret", "shop-trust-chain")]["data"]
                self.assertEqual(base64.b64decode(data["signing.pfx"]), PFX)
        written = yaml.safe_load((common.STATE / "shop/config.yaml").read_text())
        self.assertNotIn(common.MOUNTS, written)
        self.process.reset_mock()
        self.volumes.add("shop-trust-chain")  # Podman created it at install.
        deploy.uninstall("shop", delete_data=True)
        removed = [
            args[-1]
            for args in self.commands()
            if args[:3] == ["podman", "volume", "rm"]
        ]
        self.assertIn("shop-trust-chain", removed)

    def test_validate_names_the_secret_without_reading_it(self):
        self.product()
        self.deliver(common.BUILD / "dev/shop")
        trust = str(common.BUILD / "dev/shop/credentials/trust")
        real_open, real_os_open = io.open, os.open

        def guarded(opener):
            def open_file(file, *args, **kwargs):
                if str(file).startswith(trust):
                    raise AssertionError("validate opened a credential file")
                return opener(file, *args, **kwargs)

            return open_file

        stream = io.StringIO()
        with ExitStack() as guards:
            for name, opener in (
                ("io.open", real_open),
                ("builtins.open", real_open),
                ("os.open", real_os_open),
            ):
                guards.enter_context(mock.patch(name, guarded(opener)))
            guards.enter_context(redirect_stdout(stream))
            guards.enter_context(redirect_stderr(stream))
            validation.validate()
        self.assertIn(
            "[OK] shop/main: MOUNTS -> /sql/10-roles.sql, /run/secrets/trust/root.crt, "
            "/run/secrets/trust/ca.crt, /etc/ssl/certs/shop-ca.pem "
            "(Secret shop-main-files: shop-database-password; "
            "unchanged from Secret shop-trust-chain)",
            stream.getvalue(),
        )
        self.assertIn(
            "[OK] shop/migrate: MOUNTS -> /run/certificates/signing.pfx "
            "(unchanged from Secret shop-trust-chain)",
            stream.getvalue(),
        )

    def test_a_key_no_source_provides_stops_install_before_any_write(self):
        """init-config accepts it (credentials may follow); install refuses at once."""

        def wrong_key(shop):
            shop["mounts"]["main"]["/password"] = (
                "@@secret:shop-database-password/wrong@@"
            )

        self.product(wrong_key)
        releases = self.build_and_unpack()
        self.use_root(releases["shop"])
        deploy.init_config("shop")
        self.deliver(common.STATE / "shop")
        before = self.tree(common.STATE)
        self.process.reset_mock()
        with self.assertRaisesRegex(
            common.DeployError,
            r"MOUNTS\.main\./password: shop-database-password has no key wrong; "
            "it provides value",
        ):
            deploy.install()
        self.assertEqual(self.tree(common.STATE), before)
        self.assertFalse((common.STATE / "shop/credentials/database/value").exists())
        self.assertFalse(common.QUADLET_DIR.exists())
        self.assertNotIn(
            "load", [args[1] for args in self.commands() if args[0] == "podman"]
        )

    def test_a_secret_used_only_by_mounts_counts_as_used(self):
        def only_secrets(shop):
            shop["mounts"] = {"main": {"/ca.crt": "@@secret:shop-trust-chain/ca.crt@@"}}
            del shop["files"]

        self.product(only_secrets)
        self.deliver(common.BUILD / "dev/shop")
        deploy.prepare()
        rendered = documents(common.BUILD / "install.yaml")
        self.assertNotIn(("Secret", "shop-main-files"), rendered)

    def test_declaration_errors_name_the_mounts_entry_and_fail_before_writes(self):
        def source(value, container="main", target="/run/x"):
            return lambda shop: (
                shop["mounts"].setdefault(container, {}).update({target: value})
            )

        def volume(shop):
            shop["manifests"][0]["spec"]["volumes"].append(
                {"name": "shop-trust-chain-mount", "emptyDir": {}}
            )

        for label, change, pattern in (
            (
                "undeclared secret",
                source("@@secret:shop-trust-chian/ca.crt@@"),
                (
                    r"MOUNTS\.main\./run/x: SECRET_FILES has no shop-trust-chian; "
                    "declared: shop-database-password, shop-trust-chain"
                ),
            ),
            (
                "missing key",
                source("@@secret:shop-trust-chain/intermediate.crt@@"),
                (
                    r"components/shop/config.defaults.yaml: MOUNTS\.main\./run/x: "
                    "shop-trust-chain has no key intermediate.crt; it provides ca.crt, "
                    "root.crt, signing.pfx. Fix the key, or deliver a file named "
                    "intermediate.crt in shop-trust-chain's source"
                ),
            ),
            (
                "text around the reference",
                source("@@secret:shop-trust-chain/ca.crt@@.bak"),
                r"MOUNTS\.main\./run/x: a secret file is exactly one whole reference",
            ),
            (
                "not a secret reference",
                source("@@DB_USER@@"),
                "a secret file is exactly one whole reference",
            ),
            (
                "another component's secret",
                source("@@secret:other-tokens/value@@"),
                r"MOUNTS\.main\./run/x: other-tokens is another component's secret",
            ),
            (
                "unknown container",
                source("@@secret:shop-trust-chain/ca.crt@@", container="worker"),
                "exactly one container named worker; it has 0",
            ),
            (
                "target taken by the manifest",
                source(
                    "@@secret:shop-trust-chain/ca.crt@@",
                    target="/mnt/shop-database-password",
                ),
                "/mnt/shop-database-password is also a volumeMount in the manifest",
            ),
            (
                "volume name taken",
                volume,
                "already has a volume named shop-trust-chain-mount",
            ),
        ):
            with self.subTest(label):
                self.product(change)
                self.deliver(common.BUILD / "dev/shop")
                # An earlier dev state: config and a registration file.
                (common.BUILD / "dev/shop/config.yaml").write_text("DB_USER: earlier\n")
                routes = common.BUILD / "dev/routes"
                routes.mkdir(parents=True, exist_ok=True)
                (routes / "earlier.conf").write_text("location /earlier {}\n")
                before = self.tree(common.BUILD)
                with self.assertRaisesRegex(common.DeployError, pattern):
                    deploy.prepare()
                self.assertEqual(self.tree(common.BUILD), before)
