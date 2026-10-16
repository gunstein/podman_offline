"""Verify the disposable real-init harness construction and failure cleanup locally."""

import contextlib
import copy
import io
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import database_test
import yaml


class DatabaseInitHarnessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.client = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "db-check-disposable-identity"},
            "spec": {
                "restartPolicy": "Never",
                "containers": [
                    {
                        "name": "app",
                        "image": "identity:fixture",
                        "args": ["--database-check"],
                        "env": [
                            {"name": name, "value": value}
                            for name, value in (
                                ("DB_HOST", "disposable-postgres"),
                                ("DB_PORT", "5544"),
                                ("DB_USER", "configured-user"),
                                ("DB_NAME", "configured-database"),
                            )
                        ],
                        "volumeMounts": [
                            {
                                "name": "password",
                                "mountPath": "/run/secrets/database",
                                "readOnly": True,
                            }
                        ],
                    }
                ],
                "volumes": [
                    {
                        "name": "password",
                        "secret": {
                            "secretName": "disposable-secret",
                            "items": [{"key": "password", "path": "password"}],
                        },
                    }
                ],
            },
        }

    def test_replay_uses_actual_init_and_verifies_existing_rows_without_changing_inputs(
        self,
    ):
        commands, manifests = [], []
        original = copy.deepcopy(self.client)

        def podman(arguments):
            commands.append(arguments)
            if arguments[:2] == ["kube", "play"]:
                manifests.append(yaml.safe_load(Path(arguments[-1]).read_text()))
            return types.SimpleNamespace(stdout="0")

        with (
            mock.patch.object(database_test, "podman", side_effect=podman),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            database_test.init_schema_check(
                self.base, "disposable-network", self.client
            )
        self.assertEqual(
            [command[:2] for command in commands],
            [
                ["kube", "play"],
                ["wait", "db-check-disposable-identity-schema-check"],
                ["kube", "down"],
            ]
            * 2,
        )
        self.assertEqual(self.client, original)
        first, second = manifests
        init = first["spec"]["initContainers"][0]
        self.assertEqual(init["command"], ["python", "/app/schema.py"])
        self.assertEqual(init["image"], database_test.image("app1", "backend"))
        self.assertEqual(init["env"], original["spec"]["containers"][0]["env"])
        self.assertEqual(first["spec"]["volumes"], original["spec"]["volumes"])
        for document in manifests:
            script = document["spec"]["containers"][0]["command"][-1]
            self.assertNotIn("\n", script)
            compile(script, "schema-probe", "exec")
            self.assertIn("db.commit()", script)
            self.assertIn("db.close()", script)
        initial = first["spec"]["containers"][0]["command"][-1]
        replay = second["spec"]["containers"][0]["command"][-1]
        self.assertIn("assert rows == []", initial)
        self.assertIn("INSERT INTO todos", initial)
        self.assertIn("retained todo", replay)
        self.assertNotIn("INSERT INTO todos", replay)

    def test_kube_failure_identifies_fixture_without_private_diagnostics(self):
        """Distinguish schema probes from Identity without printing Podman stderr."""
        for action in ("play", "down"):
            with (
                self.subTest(action=action),
                mock.patch.object(
                    database_test.subprocess,
                    "run",
                    return_value=types.SimpleNamespace(
                        returncode=125, stdout="PRIVATE stdout", stderr="PRIVATE stderr"
                    ),
                ),
                self.assertRaisesRegex(
                    RuntimeError, "kube " + action + r" schema-init\.yaml"
                ) as failure,
            ):
                database_test.podman(
                    ["kube", action, str(self.base / "schema-init.yaml")]
                )
            self.assertNotIn("PRIVATE", str(failure.exception))

    def test_failed_probe_stops_before_replay_and_removes_disposable_pod(self):
        with (
            mock.patch.object(
                database_test, "podman", return_value=types.SimpleNamespace(stdout="1")
            ) as podman,
            self.assertRaisesRegex(RuntimeError, "init ordering or retained-data"),
        ):
            database_test.init_schema_check(
                self.base, "disposable-network", self.client
            )
        self.assertEqual(podman.call_count, 3)
        self.assertEqual(podman.call_args.args[0][:2], ["kube", "down"])
