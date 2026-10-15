"""Database lifecycle/config tests; actual authentication is tested in the lab."""

import base64
import importlib.util
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path
from unittest import mock

import yaml
from test_deploy import DeployFixture

import deploy

REPO = Path(__file__).resolve().parent.parent


class DatabaseTests(DeployFixture):
    """Use actual database manifests and disposable component secret state."""

    def setUp(self):
        super().setUp()
        shutil.copytree(REPO / "components", self.root / "components")
        shutil.copytree(
            REPO / "config",
            self.root / "config",
            ignore=shutil.ignore_patterns("dev.yaml"),
        )
        self.path = deploy.HOME / "app1/config.yaml"
        self.settings = deploy.component_defaults("app1")
        self.password = self.path.parent / "generated-certificates/database/password"
        self.manifests = deploy.ROOT / "components/app1/manifests"
        self.process.return_value = subprocess.CompletedProcess([], 1)

    def preflight(self):
        deploy.database_preflight(self.settings, self.path, self.manifests)

    def test_new_database_generates_once_with_private_modes(self):
        self.preflight()
        deploy.generate_secrets(self.settings, self.path.parent)
        before = self.password.read_bytes()
        self.assertEqual(len(before), 32)
        self.assertEqual(self.mode(self.password), 0o600)
        self.assertEqual(self.mode(self.password.parent), 0o700)
        self.process.reset_mock()
        self.preflight()
        deploy.generate_secrets(self.settings, self.path.parent)
        self.assertEqual(self.password.read_bytes(), before)
        self.process.assert_not_called()

    def test_app_passwords_are_generated_independently(self):
        passwords = []
        for component in ("app1", "app2"):
            config = deploy.component_defaults(component)
            base = deploy.HOME / component
            deploy.database_preflight(
                config,
                base / "config.yaml",
                deploy.ROOT / "components" / component / "manifests",
            )
            deploy.generate_secrets(config, base)
            passwords.append(
                (base / "generated-certificates/database/password").read_bytes()
            )
        self.assertNotEqual(passwords[0], passwords[1])

    def test_generated_password_is_the_shared_kube_secret_and_never_a_placeholder(self):
        self.write("home/app1/config.yaml", yaml.safe_dump(self.settings))
        self.write("home/app1/generated-certificates/todo/public-fixture", b"fixture")
        self.preflight()
        text = deploy.render(
            config_path=self.path, manifests=self.manifests, component="app1"
        )
        password = self.password.read_bytes()
        docs = list(yaml.safe_load_all(text))
        secret = next(
            d
            for d in docs
            if d["kind"] == "Secret"
            and d["metadata"]["name"] == "app1-database-password"
        )
        self.assertEqual(base64.b64decode(secret["data"]["password"]), password)
        self.assertNotIn(password.decode(), text)
        self.assertNotIn("ConnectionStrings__Default", text)
        self.assertNotIn("@@", text)
        deploy.render(config_path=self.path, manifests=self.manifests, component="app1")
        self.assertEqual(self.password.read_bytes(), password)

    def test_production_volume_guard_precedes_images_and_persistent_changes(self):
        self.write(
            "bundle.yaml",
            "name: app1\ncomponents: [app1]\nrequires: {platform: {min: 0.4.0, before: 0.5.0}, identity: {min: 0.4.0, before: 0.5.0}}\n",
        )
        self.write("VERSION", "0.2.1\n")
        self.write("PLATFORM_VERSION", "0.2.1\n")
        self.write("home/installed/platform", "0.4.0\n")
        self.write("home/installed/identity", "0.4.0\n")
        self.write(
            "home/platform/config.yaml",
            yaml.safe_dump(deploy.component_defaults("platform")),
        )
        self.write("home/app1/config.yaml", yaml.safe_dump(self.settings))
        before = {p: p.read_bytes() for p in deploy.HOME.rglob("*") if p.is_file()}
        self.process.return_value = subprocess.CompletedProcess([], 0)
        with self.assertRaisesRegex(deploy.DeployError, "existing volume app1-data"):
            deploy.install_components()
        self.assertEqual(
            before, {p: p.read_bytes() for p in deploy.HOME.rglob("*") if p.is_file()}
        )
        self.assertEqual(self.process.call_count, 1)
        self.assertFalse(self.password.exists())

    def test_legacy_config_missing_db_additions_stops_before_commands_or_writes(self):
        """Each README-required DB key is mandatory even when new defaults supply it."""
        self.write(
            "bundle.yaml",
            "name: app1\ncomponents: [app1]\nrequires: {platform: {min: 0.4.0, before: 0.5.0}, identity: {min: 0.4.0, before: 0.5.0}}\n",
        )
        self.write("VERSION", "0.2.1\n")
        self.write("PLATFORM_VERSION", "0.2.1\n")
        self.write("home/installed/platform", "0.4.0\n")
        self.write("home/installed/identity", "0.4.0\n")
        self.write("IDENTITY_VERSION", "0.4.1\n")
        self.write(
            "home/platform/config.yaml",
            yaml.safe_dump(deploy.component_defaults("platform")),
        )
        identity = deploy.component_defaults("identity")
        self.write("home/identity/config.yaml", yaml.safe_dump(identity))
        for component, settings in (("identity", identity), ("app1", self.settings)):
            for key in ("DB_HOST", "DB_PORT", "DB_USER", "DB_NAME"):
                with self.subTest(component=component, key=key):
                    self.write("home/identity/config.yaml", yaml.safe_dump(identity))
                    self.write("home/app1/config.yaml", yaml.safe_dump(self.settings))
                    legacy = dict(settings)
                    del legacy[key]
                    self.write(
                        "home/" + component + "/config.yaml", yaml.safe_dump(legacy)
                    )
                    before = {
                        p: p.read_bytes() for p in deploy.HOME.rglob("*") if p.is_file()
                    }
                    self.write(
                        "bundle.yaml",
                        yaml.safe_dump(
                            {
                                "name": component,
                                "components": [component],
                                "requires": {
                                    dependency: {"min": "0.4.0", "before": "0.5.0"}
                                    for dependency in deploy.DEPENDENCIES[component]
                                },
                            }
                        ),
                    )
                    self.process.reset_mock()
                    with self.assertRaisesRegex(deploy.DeployError, "Missing " + key):
                        deploy.install_components()
                    self.process.assert_not_called()
                    self.assertEqual(
                        before,
                        {
                            p: p.read_bytes()
                            for p in deploy.HOME.rglob("*")
                            if p.is_file()
                        },
                    )

    def test_existing_credentials_survive_transition_byte_for_byte(self):
        content = b""" space;both'"$= end \n\n"""
        self.write("home/app1/generated-certificates/database/password", content, 0o600)
        self.preflight()
        deploy.generate_secrets(self.settings, self.path.parent)
        self.assertEqual(self.password.read_bytes(), content)
        self.process.assert_not_called()
        self.assertNotIn(content.decode(), self.stdout.getvalue())

    def test_existing_volume_without_password_refuses_before_all_generation(self):
        self.process.return_value = subprocess.CompletedProcess([], 0)
        with self.assertRaisesRegex(deploy.DeployError, "app1-data.*restore.*backup"):
            self.preflight()
        self.assertFalse(self.password.parent.exists())
        self.assertFalse(
            (self.path.parent / "generated-certificates/todo/session-key").exists()
        )
        self.process.assert_called_once_with(
            ["podman", "volume", "exists", "app1-data"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_empty_invalid_or_unreadable_password_never_replaced(self):
        for content in (b"", b"\n\n", b"a\x00b", b"a\nb", b"a\r\n", b"\xff"):
            with self.subTest(kind=repr(content)):
                self.write(
                    "home/app1/generated-certificates/database/password", content
                )
                with self.assertRaisesRegex(deploy.DeployError, "password.*restore"):
                    self.preflight()
                self.assertEqual(self.password.read_bytes(), content)
        self.process.assert_not_called()

    def test_volume_check_error_is_not_absence(self):
        for code in (2, 125):
            self.process.return_value = subprocess.CompletedProcess([], code)
            with self.assertRaisesRegex(
                deploy.DeployError, "Cannot check database volume app1-data"
            ):
                self.preflight()
        self.process.side_effect = OSError("private details")
        with self.assertRaisesRegex(deploy.DeployError, "no password generated"):
            self.preflight()
        self.assertFalse(self.password.exists())
        self.assertNotIn("private details", self.stderr.getvalue())

    def test_non_regular_password_is_refused_without_opening_it(self):
        self.password.parent.mkdir(parents=True)
        os.mkfifo(str(self.password), 0o600)
        with self.assertRaisesRegex(
            deploy.DeployError, "Invalid database password file"
        ):
            self.preflight()
        self.process.assert_not_called()

    def test_missing_generation_declaration_requires_manual_config_addition(self):
        self.settings[deploy.GENERATED_SECRETS] = []
        with self.assertRaisesRegex(
            deploy.DeployError, "GENERATED_SECRETS.*config.yaml"
        ):
            self.preflight()
        self.assertFalse(self.password.exists())

    def test_all_components_share_their_secret_and_public_database_parameters(self):
        for component in ("identity", "app1", "app2"):
            config = deploy.component_defaults(component)
            config["PUBLIC_HOSTNAME"] = "myproduct-proxy"
            docs = []
            for path in (deploy.ROOT / "components" / component / "manifests").glob(
                "*.yaml"
            ):
                docs.extend(deploy.replace(deploy.load_yaml_all(path), config))
            pods = [d for d in docs if d.get("kind") == "Pod"]
            server = next(p for p in pods if p["metadata"]["name"].endswith("postgres"))
            client = next(
                p for p in pods if p["metadata"]["name"].endswith(("server", "todo"))
            )
            server_env = {
                e["name"]: e["value"] for e in server["spec"]["containers"][0]["env"]
            }
            client_env = {
                e["name"]: e["value"] for e in client["spec"]["containers"][0]["env"]
            }
            self.assertEqual(server_env["POSTGRES_USER"], client_env["DB_USER"])
            self.assertEqual(server_env["POSTGRES_DB"], client_env["DB_NAME"])
            self.assertEqual(server_env["PGPORT"], client_env["DB_PORT"])
            for value in client_env.values():
                self.assertIsInstance(value, str)
            for pod in (server, client):
                volume = next(
                    v for v in pod["spec"]["volumes"] if v["name"] == "password"
                )
                self.assertEqual(
                    volume["secret"]["secretName"], component + "-database-password"
                )
                self.assertEqual(
                    volume["secret"]["items"], [{"key": "password", "path": "password"}]
                )
            relative = "identity-db" if component == "identity" else "database"
            self.assertIn(
                "generated-certificates/" + relative + "/password",
                config[deploy.GENERATED_SECRETS],
            )
            serialized = yaml.safe_dump(docs)
            self.assertNotIn("ConnectionStrings__Default", serialized)
            self.assertNotIn("DB_PASSWORD", config)

    def test_port_and_missing_parameters_fail_without_values(self):
        for port in (5432, "0", "65536", "password-sensitive", "1;Password=x"):
            config = dict(self.settings, DB_PORT=port)
            with self.assertRaisesRegex(
                deploy.DeployError, "DB_PORT.*config.yaml"
            ) as caught:
                deploy.validate_config(config, self.path)
            self.assertNotIn(str(port) + ";", str(caught.exception))
        for key in ("DB_HOST", "DB_PORT", "DB_USER", "DB_NAME"):
            config = dict(self.settings)
            del config[key]
            with self.assertRaisesRegex(deploy.DeployError, key):
                deploy.validate_component_config(config, "app1", self.path)

    def test_shared_dev_port_override_does_not_require_a_database_in_help(self):
        self.write("config/dev.yaml", 'DB_PORT: "5544"\n')
        for component in deploy.COMPONENTS:
            self.assertEqual(
                deploy.component_defaults(component, dev=True)["DB_PORT"], "5544"
            )
        self.assertNotIn("DB_HOST", deploy.component_defaults("help", dev=True))

    def test_dev_checks_all_databases_before_config_or_secret_writes(self):
        self.process.side_effect = [
            subprocess.CompletedProcess([], 1),
            subprocess.CompletedProcess([], 0),
        ]
        with self.assertRaisesRegex(deploy.DeployError, "existing volume app1-data"):
            deploy.prepare_components()
        self.assertFalse((deploy.BUILD / "dev").exists())


class PythonDatabaseTests(DeployFixture):
    """Execute Python's actual secret reader with a stubbed psycopg transport."""

    def setUp(self):
        super().setUp()
        driver = types.ModuleType("psycopg")
        rows = types.ModuleType("psycopg.rows")
        rows.__dict__.update(DictRow=dict, dict_row=object())
        self.transport = mock.Mock()
        driver.__dict__["Connection"] = mock.Mock()
        driver.__dict__["Connection"].__getitem__ = mock.Mock(
            return_value=self.transport
        )
        self.stack.enter_context(
            mock.patch.dict(sys.modules, {"psycopg": driver, "psycopg.rows": rows})
        )
        spec = importlib.util.spec_from_file_location(
            "db_fixture", REPO / "apps/todo-backend/database.py"
        )
        assert spec is not None and spec.loader is not None
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.stack.enter_context(
            mock.patch.dict(
                os.environ,
                {
                    "DB_HOST": "test-db",
                    "DB_PORT": "5544",
                    "DB_USER": "test-user",
                    "DB_NAME": "test-name",
                },
            )
        )

    def test_special_credentials_preserve_spaces_and_only_strip_trailing_lf(self):
        password = """ spaces;single' double" dollar$ equals= end """
        with mock.patch.object(
            Path, "read_bytes", return_value=(password + "\n\n").encode()
        ):
            values = self.module.parameters()
        self.assertEqual(
            values,
            {
                "host": "test-db",
                "port": 5544,
                "user": "test-user",
                "dbname": "test-name",
                "password": password,
            },
        )

    def test_parameter_failures_do_not_expose_credentials(self):
        invalid_port = mock.patch.dict(os.environ, {"DB_PORT": "sensitive-password"})
        failure = self.assertRaisesRegex(RuntimeError, "Invalid DB_PORT")
        with invalid_port, failure as error:
            self.module.parameters()
        self.assertNotIn("sensitive-password", str(error.exception))
        for content in (b"", b"\n", b"a\x00", b"\xff", b"a\nb", b"a\r\n"):
            reader = mock.patch.object(Path, "read_bytes", return_value=content)
            failure = self.assertRaisesRegex(RuntimeError, "password file")
            with reader, failure:
                self.module.parameters()

    def test_handshake_authentication_is_distinguished_from_transport_failures(self):
        for message, expected in (
            (b'FATAL:  password authentication failed for user "todo"', True),
            (b"could not translate host name", False),
            (b"connection refused", False),
            (b"connection timed out", False),
        ):
            error = types.SimpleNamespace(
                sqlstate=None, pgconn=types.SimpleNamespace(error_message=message)
            )
            self.assertEqual(self.module.authentication_failed(error), expected)
        self.assertTrue(
            self.module.authentication_failed(types.SimpleNamespace(sqlstate="28P01"))
        )
        self.assertFalse(
            self.module.authentication_failed(types.SimpleNamespace(sqlstate=None))
        )
        self.assertTrue(
            self.module.authentication_failed(
                RuntimeError('FATAL:  password authentication failed for user "todo"')
            )
        )
        self.assertFalse(
            self.module.authentication_failed(
                RuntimeError("could not translate host name")
            )
        )
