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


def mounted_orders():
    """orders with its password mounted as one file through MOUNTS (backlog 82).

    The manifest keeps POSTGRES_PASSWORD_FILE and the data PVC; the password
    Secret's volume and mount are gone and come from MOUNTS instead.
    """
    product = copy.deepcopy(RENAMED)
    orders = product["orders"]
    spec = orders["manifests"][1]["spec"]
    db = spec["containers"][0]
    db["volumeMounts"] = [
        m for m in db["volumeMounts"] if m["mountPath"] != "/run/secrets/database"
    ]
    spec["volumes"] = [v for v in spec["volumes"] if "secret" not in v]
    orders["mounts"] = {
        "db": {
            "/run/secrets/database/password": "@@secret:orders-database-password/password@@"
        }
    }
    return product


def binding(mounts, items):
    """postgres_binding for one db container with the given mounts and Secret items."""
    pod = {"metadata": {"name": "orders-postgres"}}
    container = {
        "name": "db",
        "env": [
            {
                "name": "POSTGRES_PASSWORD_FILE",
                "value": "/run/secrets/database/password",
            }
        ],
        "volumeMounts": [{"name": "data", "mountPath": "/var/lib/postgresql/data"}]
        + mounts,
    }
    spec = {
        "volumes": [
            {"name": "data", "persistentVolumeClaim": {"claimName": "orders-data"}},
            {
                "name": "pw",
                "secret": {"secretName": "orders-database-password", "items": items},
            },
        ]
    }
    return deploy.postgres_binding(pod, spec, "containers", container)


class MountedPasswordTests(ProductFixture):
    """The database password as a MOUNTS secret file keeps the password guard."""

    def setUp(self):
        super().setUp()
        self.product = mounted_orders()
        self.write_product(self.product)
        self.dev = common.BUILD / "dev"
        self.provide_credentials(self.product, self.dev)
        self.password = self.dev / "orders/credentials/database/password"

    def volume_checks(self):
        return [args for args in self.commands() if args[:2] == ["podman", "volume"]]

    def test_new_database_generates_once_and_keeps_the_password(self):
        deploy.prepare()
        self.assertEqual(
            self.volume_checks(), [["podman", "volume", "exists", "orders-data"]]
        )
        before = self.password.read_bytes()
        self.assertEqual(len(before), 32)
        self.process.reset_mock()
        deploy.prepare()
        self.assertEqual(self.password.read_bytes(), before)
        self.assertEqual(self.volume_checks(), [])

    def test_existing_volume_without_password_stops_before_generation(self):
        self.volumes.add("orders-data")
        before = self.files_under(self.dev)
        with self.assertRaisesRegex(
            common.DeployError, "with existing volume orders-data; .*no password"
        ):
            deploy.prepare()
        self.assertFalse(self.password.exists())
        self.assertEqual(self.files_under(self.dev), before)


class PasswordMountShapeTests(ProductFixture):
    """Both mount shapes name the same claim, Secret and key; others are refused."""

    def test_directory_and_single_file_mounts(self):
        for label, mounts, items in (
            (
                "directory",
                [{"name": "pw", "mountPath": "/run/secrets/database"}],
                [{"key": "password", "path": "password"}],
            ),
            (
                "directory, key differs from path",
                [{"name": "pw", "mountPath": "/run/secrets/database"}],
                [{"key": "db-admin", "path": "password"}],
            ),
            (
                "single file",
                [
                    {
                        "name": "pw",
                        "mountPath": "/run/secrets/database/password",
                        "subPath": "password",
                        "readOnly": True,
                    }
                ],
                [{"key": "password", "path": "password"}],
            ),
            (
                "single file, key differs from path",
                [
                    {
                        "name": "pw",
                        "mountPath": "/run/secrets/database/password",
                        "subPath": "pw.txt",
                    }
                ],
                [
                    {"key": "other", "path": "other.txt"},
                    {"key": "db-admin", "path": "pw.txt"},
                ],
            ),
        ):
            with self.subTest(label):
                expected_key = "db-admin" if "differs" in label else "password"
                self.assertEqual(
                    binding(mounts, items),
                    ("orders-data", "orders-database-password", expected_key),
                )

    def test_wrong_mounts_are_refused_without_guessing(self):
        single = {"name": "pw", "mountPath": "/run/secrets/database/password"}
        items = [{"key": "password", "path": "password"}]
        for label, mounts, secret_items, pattern in (
            ("wrong subPath", [dict(single, subPath="pass")], items, "Secret/PVC binding"),
            ("no subPath", [single], items, "with subPath"),
            ("no matching item", [dict(single, subPath="password")],
             [{"key": "password", "path": "other"}], "Secret/PVC binding"),
            ("wrong target", [{"name": "pw", "mountPath": "/run/secrets/db/password",
                               "subPath": "password"}], items,
             "single file /run/secrets/database/password with subPath"),
            ("both shapes", [dict(single, subPath="password"),
                             {"name": "pw", "mountPath": "/run/secrets/database"}],
             items, "either as the directory /run/secrets/database"),
        ):  # fmt: skip
            with self.subTest(label), self.assertRaisesRegex(
                common.DeployError, pattern
            ) as failure:
                binding(mounts, secret_items)
            self.assertIn("container 'db'", str(failure.exception))
