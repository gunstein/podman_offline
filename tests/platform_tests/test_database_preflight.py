"""Database preflight on the effective manifest (backlog item 21, section 1 and F2).

The volume, Secret and password path may come from config placeholders; Podman
must be asked about the configured volume, never a literal @@NAME@@. Password
settings other than the supported POSTGRES_PASSWORD_FILE layout are refused.
"""

import copy
import shutil
import subprocess

from deployment import common, deploy

from helpers.product_fixture import RENAMED, ProductFixture


def configured_orders():
    """orders with its volume, Secret and password path taken from config."""
    product = copy.deepcopy(RENAMED)
    orders = product["orders"]
    orders["defaults"].update(
        {
            "DB_VOLUME": "orders-data",
            "DB_SECRET": "orders-database-password",
            "DB_PASSWORD_FILE": "/run/secrets/database/password",
        }
    )
    spec = orders["manifests"][1]["spec"]
    spec["containers"][0]["env"][1]["value"] = "@@DB_PASSWORD_FILE@@"
    spec["volumes"][0]["persistentVolumeClaim"]["claimName"] = "@@DB_VOLUME@@"
    spec["volumes"][1]["secret"]["secretName"] = "@@DB_SECRET@@"
    return product


class ConfiguredDatabaseTests(ProductFixture):
    def setUp(self):
        super().setUp()
        self.product = configured_orders()
        self.write_product(self.product)
        self.dev = common.BUILD / "dev"
        self.provide_credentials(self.product, self.dev)
        self.password = self.dev / "orders/credentials/database/password"

    def volume_checks(self):
        return [args for args in self.commands() if args[:2] == ["podman", "volume"]]

    def test_absent_configured_volume_allows_generation(self):
        deploy.prepare()
        self.assertEqual(
            self.volume_checks(), [["podman", "volume", "exists", "orders-data"]]
        )
        self.assertTrue(self.password.is_file())
        before = self.password.read_bytes()
        self.process.reset_mock()
        deploy.prepare()  # Existing password: kept byte for byte, no volume check.
        self.assertEqual(self.password.read_bytes(), before)
        self.assertEqual(self.volume_checks(), [])

    def test_existing_configured_volume_refuses_before_any_write(self):
        self.volumes.add("orders-data")
        before = self.files_under(self.dev)
        with self.assertRaisesRegex(
            common.DeployError, "with existing volume orders-data; .*no password"
        ):
            deploy.prepare()
        self.assertEqual(
            self.volume_checks(), [["podman", "volume", "exists", "orders-data"]]
        )
        self.assertEqual(self.files_under(self.dev), before)

    def test_inspection_errors_are_not_absence(self):
        def failing(arguments, **kwargs):
            if list(arguments)[:3] == ["podman", "volume", "exists"]:
                return subprocess.CompletedProcess(arguments, 125, b"", b"private")
            return self.host_command(arguments, **kwargs)

        for side_effect in (failing, OSError("no podman")):
            with self.subTest(side_effect=side_effect):
                self.process.side_effect = side_effect
                with self.assertRaisesRegex(
                    common.DeployError,
                    "Cannot check database volume orders-data; no password generated",
                ):
                    deploy.prepare()
                self.assertFalse(self.password.exists())

    def test_install_checks_the_configured_volume(self):
        releases = self.build_and_unpack()
        shutil.rmtree(self.source)
        self.provide_credentials(self.product, common.STATE)
        for name in ("gateway", "login-service"):
            self.install(releases[name])
        self.use_root(releases["orders"])
        deploy.init_config("orders")
        self.volumes.add("orders-data")
        before = self.files_under(common.STATE)
        self.process.reset_mock()
        with self.assertRaisesRegex(common.DeployError, "existing volume orders-data"):
            deploy.install()
        self.assertEqual(
            self.commands(), [["podman", "volume", "exists", "orders-data"]]
        )
        self.assertEqual(self.files_under(common.STATE), before)


class UnsupportedPasswordSettingTests(ProductFixture):
    """F2: other password forms would skip the guard; refuse them before writes."""

    def test_other_password_settings_are_refused(self):
        for group in ("containers", "initContainers"):
            for entry in (
                {"name": "POSTGRES_PASSWORD", "value": "x"},
                {
                    "name": "POSTGRES_PASSWORD",
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "orders-database-password",
                            "key": "password",
                        }
                    },
                },
                {
                    "name": "POSTGRES_PASSWORD_FILE",
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "orders-database-password",
                            "key": "password",
                        }
                    },
                },
            ):
                with self.subTest(group=group, entry=entry):
                    product = copy.deepcopy(RENAMED)
                    spec = product["orders"]["manifests"][1]["spec"]
                    container = spec["containers"][0]
                    container["env"] = [
                        e
                        for e in container["env"]
                        if e["name"] != "POSTGRES_PASSWORD_FILE"
                    ] + [entry]
                    if group == "initContainers":
                        spec["initContainers"] = [spec.pop("containers")[0]]
                        spec["containers"] = [
                            {
                                "name": "web",
                                "image": "localhost/postgres:17",
                                "imagePullPolicy": "Never",
                            }
                        ]
                    shutil.rmtree(self.root / "source", ignore_errors=True)
                    self.write_product(product)
                    self.process.reset_mock()
                    with self.assertRaisesRegex(
                        common.DeployError,
                        f"POSTGRES_PASSWORD.* in container 'db' \\({group}\\) of Pod 'orders-postgres'",
                    ):
                        deploy.prepare()
                    self.assertEqual(self.commands(), [])
                    self.assertFalse((common.BUILD / "dev").exists())


class DataDirectoryDetectionTests(ProductFixture):
    """A container mounting the PostgreSQL data directory is a database container."""

    def test_data_mount_without_supported_password_file_is_refused(self):
        for case in ("PGPASSWORD", "envFrom", "no password"):
            with self.subTest(case=case):
                product = copy.deepcopy(RENAMED)
                spec = product["orders"]["manifests"][1]["spec"]
                container = spec["containers"][0]
                container["env"] = [
                    e for e in container["env"] if e["name"] != "POSTGRES_PASSWORD_FILE"
                ]
                if case == "PGPASSWORD":
                    container["env"].append(
                        {
                            "name": "PGPASSWORD",
                            "valueFrom": {
                                "secretKeyRef": {
                                    "name": "orders-database-password",
                                    "key": "password",
                                }
                            },
                        }
                    )
                elif case == "envFrom":
                    container["envFrom"] = [
                        {"secretRef": {"name": "orders-database-password"}}
                    ]
                shutil.rmtree(self.root / "source", ignore_errors=True)
                self.write_product(product)
                self.process.reset_mock()
                with self.assertRaisesRegex(
                    common.DeployError,
                    "Unsupported PostgreSQL password setting \\(none\\) in container 'db'",
                ):
                    deploy.prepare()
                self.assertEqual(self.commands(), [])
                self.assertFalse((common.BUILD / "dev").exists())
