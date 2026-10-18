"""Actual app1 init declarations and schema code; no claim of Podman execution."""

import ast
import contextlib
import importlib.util
import io
import os
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import yaml
from catalog_fixture import write_secret_fixtures
from render_helper import materialize_and_render

import bundle
from deployment import render as rendering

ROOT = Path(__file__).resolve().parent.parent


class DriverError(Exception):
    def __init__(self, sqlstate=None):
        super().__init__("private-driver-message Password=sensitive Host=private")
        self.sqlstate = sqlstate


class InitDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.database = types.ModuleType("database")
        self.database.__dict__.update(
            parameters=mock.Mock(),
            connect=mock.MagicMock(),
            authentication_failed=lambda error: error.sqlstate == "28P01",
        )
        driver = types.ModuleType("psycopg")
        driver.__dict__["Error"] = DriverError
        with mock.patch.dict(
            sys.modules, {"database": self.database, "psycopg": driver}
        ):
            spec = importlib.util.spec_from_file_location(
                "todo_schema_fixture", ROOT / "apps/todo-backend/schema.py"
            )
            assert spec is not None and spec.loader is not None
            self.schema = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.schema)
        self.db = mock.MagicMock()
        self.schema.connect.return_value.__enter__.return_value = self.db
        self.clock = mock.patch.object(
            self.schema, "time", mock.Mock(monotonic=mock.Mock(return_value=0))
        )
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_rendered_app1_has_separate_earlier_database_and_same_secret_for_init(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "credentials/todo").mkdir(parents=True)
            (base / "credentials/todo/fixture").write_text("synthetic certificate")
            config = rendering.merge_config(
                ROOT / "config/common.defaults.yaml",
                ROOT / "components/app1/config.defaults.yaml",
            )
            write_secret_fixtures(base, config, "app1")
            path = base / "config.yaml"
            path.write_text(yaml.safe_dump(config))
            text = materialize_and_render(
                base / "files",
                config_path=path,
                manifests=ROOT / "components/app1/manifests",
                component="app1",
            )
            docs = list(yaml.safe_load_all(text))
            pods = [doc for doc in docs if doc["kind"] == "Pod"]
            self.assertEqual(
                [pod["metadata"]["name"] for pod in pods],
                ["app1-postgres", "app1-todo"],
            )
            server, todo = pods
            init = todo["spec"]["initContainers"][0]
            backend = todo["spec"]["containers"][0]
            self.assertEqual(
                todo["metadata"]["annotations"][
                    "io.podman.annotations.init.container.type"
                ],
                "always",
            )
            self.assertEqual(init["command"], ["python", "/app/schema.py"])
            self.assertEqual(init["image"], backend["image"])
            self.assertEqual(init["imagePullPolicy"], "Never")
            self.assertEqual(
                init["volumeMounts"],
                [
                    {
                        "name": "password",
                        "mountPath": "/run/secrets/database",
                        "readOnly": True,
                    }
                ],
            )
            self.assertEqual(
                init["env"],
                [entry for entry in backend["env"] if entry["name"].startswith("DB_")],
            )
            self.assertEqual(
                next(
                    entry["value"]
                    for entry in init["env"]
                    if entry["name"] == "DB_HOST"
                ),
                server["metadata"]["name"],
            )
            for pod in pods:
                secret = next(
                    volume
                    for volume in pod["spec"]["volumes"]
                    if volume["name"] == "password"
                )["secret"]
                self.assertEqual(secret["secretName"], "app1-database-password")
                self.assertEqual(
                    secret["items"], [{"key": "password", "path": "password"}]
                )
            images = rendering.find_images(docs)
            self.assertEqual(images.count(init["image"]), 1)
            self.assertEqual(
                images, bundle.manifest_images(ROOT / "components/app1/manifests")
            )
            before = (base / "credentials/database/password").read_bytes()
            materialize_and_render(
                base / "files",
                config_path=path,
                manifests=ROOT / "components/app1/manifests",
                component="app1",
            )
            self.assertEqual(
                (base / "credentials/database/password").read_bytes(), before
            )

    def test_backend_dispatch_requires_schema_only_for_app1_and_app2_keeps_initialization(
        self,
    ):
        app2 = rendering.load_yaml_all(ROOT / "components/app2/manifests/60-todo.yaml")[
            0
        ]
        self.assertNotIn("initContainers", app2["spec"])
        self.assertNotIn(
            "TODO_SCHEMA_MODE",
            [entry["name"] for entry in app2["spec"]["containers"][0]["env"]],
        )
        app1 = rendering.load_yaml_all(ROOT / "components/app1/manifests/60-todo.yaml")[
            0
        ]
        mode = next(
            entry["value"]
            for entry in app1["spec"]["containers"][0]["env"]
            if entry["name"] == "TODO_SCHEMA_MODE"
        )
        module = ast.parse((ROOT / "apps/todo-backend/app.py").read_text())
        # Compile a parsed module so the test remains compatible with Python 3.6.
        isolated = ast.parse("")
        isolated.body = [module.body[-1]]
        for value, expected in ((mode, "verify_ready"), (None, "initialize")):
            scope = {"os": os, "verify_ready": mock.Mock(), "initialize": mock.Mock()}
            with mock.patch.dict(os.environ, {}, clear=True):
                if value is not None:
                    os.environ["TODO_SCHEMA_MODE"] = value
                exec(compile(isolated, "backend dispatch", "exec"), scope)  # noqa: S102
            scope[expected].assert_called_once_with()
            scope[
                "initialize" if expected == "verify_ready" else "verify_ready"
            ].assert_not_called()
        scope = {
            "os": os,
            "verify_ready": mock.Mock(side_effect=RuntimeError("init failed")),
            "initialize": mock.Mock(),
        }
        environment = mock.patch.dict(os.environ, {"TODO_SCHEMA_MODE": mode})
        failure = self.assertRaisesRegex(RuntimeError, "init failed")
        with environment, failure:
            exec(compile(isolated, "backend dispatch", "exec"), scope)  # noqa: S102
        scope["initialize"].assert_not_called()

    def test_unavailable_database_is_retried_before_transactional_creation(self):
        connection = self.schema.connect.return_value
        self.schema.connect.side_effect = [DriverError("57P03"), connection]
        self.schema.prepare()
        self.assertEqual(self.schema.connect.call_count, 2)
        self.schema.time.sleep.assert_called_once_with(1)
        self.db.execute.assert_any_call(self.schema.CREATE_TABLE)
        connection.__exit__.assert_called_once_with(None, None, None)

    def test_authentication_and_sql_errors_fail_immediately_without_private_diagnostics(
        self,
    ):
        for state, message in (
            ("28P01", "authentication failed"),
            ("42501", "schema preparation failed"),
        ):
            with self.subTest(state=state):
                self.schema.connect.side_effect = DriverError(state)
                with self.assertRaisesRegex(RuntimeError, message) as caught:
                    self.schema.prepare()
                self.assertNotIn("sensitive", str(caught.exception))
                self.schema.time.sleep.assert_not_called()

    def test_connection_retry_has_a_deadline_and_does_not_create_schema_on_timeout(
        self,
    ):
        self.schema.time.monotonic.side_effect = [0, 0, 60]
        self.schema.connect.side_effect = DriverError()
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            self.schema.prepare()
        self.schema.connect.assert_called_once_with(timeout=2)
        self.db.execute.assert_not_called()

    def test_invalid_credential_input_is_not_retried(self):
        self.schema.parameters.side_effect = RuntimeError(
            "Empty or invalid database password file"
        )
        with self.assertRaisesRegex(RuntimeError, "password file"):
            self.schema.prepare()
        self.schema.connect.assert_not_called()
        self.schema.time.sleep.assert_not_called()

    def test_repeated_creation_preserves_rows_and_identity_using_sqlite_adapter(self):
        # Exercise actual DDL and transactions, adapting only PostgreSQL identity
        # syntax and connection-local SETs. This is not PostgreSQL verification.
        with sqlite3.connect(":memory:") as connection:

            class Adapter:
                def execute(self, sql):
                    if sql.startswith("SET "):
                        return None
                    return connection.execute(
                        sql.replace(
                            "bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY",
                            "INTEGER PRIMARY KEY AUTOINCREMENT",
                        )
                    )

            @contextlib.contextmanager
            def connect(**kwargs):
                with connection:
                    yield Adapter()

            self.schema.__dict__["connect"] = connect
            self.schema.prepare()
            connection.execute(
                "INSERT INTO todos(owner, title) VALUES ('alice', 'retained todo')"
            )
            connection.commit()
            before = connection.execute("SELECT * FROM todos").fetchall()
            self.schema.prepare()
            self.schema.verify_ready()
            self.assertEqual(
                connection.execute("SELECT * FROM todos").fetchall(), before
            )
            connection.execute(
                "INSERT INTO todos(owner, title) VALUES ('bob', 'new todo')"
            )
            self.assertEqual(
                connection.execute("SELECT id FROM todos ORDER BY id").fetchall(),
                [(1,), (2,)],
            )

    def test_backend_verification_never_creates_table_or_masks_failure(self):
        self.db.execute.side_effect = DriverError("42P01")
        with self.assertRaisesRegex(RuntimeError, "init must succeed"):
            self.schema.verify_ready()
        self.assertFalse(
            any("CREATE" in str(call) for call in self.db.execute.call_args_list)
        )

    def test_cli_failure_and_hard_timeout_are_sanitized_nonzero_and_cancel_alarm(self):
        for failure in (DriverError(), RuntimeError("private Password=sensitive")):
            with self.subTest(failure=type(failure).__name__):
                output, errors = io.StringIO(), io.StringIO()
                preparation = mock.patch.object(
                    self.schema, "prepare", side_effect=failure
                )
                alarm = mock.patch.object(self.schema, "signal")
                stdout = contextlib.redirect_stdout(output)
                stderr = contextlib.redirect_stderr(errors)
                with preparation, alarm as signals, stdout, stderr:
                    self.assertEqual(self.schema.main(), 1)
                self.assertEqual(
                    signals.alarm.call_args_list, [mock.call(75), mock.call(0)]
                )
                self.assertNotIn("sensitive", output.getvalue() + errors.getvalue())
                self.assertNotIn("Traceback", errors.getvalue())
                self.assertIn("Todo database preparation failed", errors.getvalue())
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            self.schema.timed_out(None, None)

    def test_cli_success_returns_zero_after_preparation_and_cancels_alarm(self):
        preparation = mock.patch.object(self.schema, "prepare")
        alarm = mock.patch.object(self.schema, "signal")
        stdout = contextlib.redirect_stdout(io.StringIO())
        with preparation as prepare, alarm as signals, stdout as output:
            self.assertEqual(self.schema.main(), 0)
        prepare.assert_called_once_with()
        self.assertIn("schema is ready", output.getvalue())
        self.assertEqual(signals.alarm.call_args_list, [mock.call(75), mock.call(0)])

    def test_real_process_alarm_interrupts_blocked_preparation_with_safe_failure(self):
        code = """
import importlib.util, signal, sys, time, types
database = types.ModuleType('database')
database.parameters = database.connect = database.authentication_failed = lambda: None
sys.modules['database'] = database
sys.modules['psycopg'] = types.ModuleType('psycopg')
spec = importlib.util.spec_from_file_location('schema', sys.argv[1])
schema = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schema)
schema.prepare = lambda: time.sleep(30)
alarm = signal.alarm
schema.signal.alarm = lambda seconds: alarm(1 if seconds else 0)
sys.exit(schema.main())
"""
        result = subprocess.run(  # noqa: UP022 - Python 3.6
            [
                sys.executable,
                "-B",
                "-c",
                code,
                str(ROOT / "apps/todo-backend/schema.py"),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,  # noqa: UP021 - Python 3.6
            check=False,
            timeout=5,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Todo database preparation failed", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
