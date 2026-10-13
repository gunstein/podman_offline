"""Verify product probes and database-independent backend liveness without Podman."""

import ast
import types
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parent.parent


class ProbeTests(unittest.TestCase):
    """Check the actual manifests and isolated backend health functions."""

    def containers(self):
        """Return every ordinary or init-container from product manifests."""
        for path in sorted((ROOT / "manifests").glob("*.yaml")):
            with path.open() as stream:
                for doc in yaml.safe_load_all(stream):
                    if isinstance(doc, dict) and doc.get("kind") == "Pod":
                        for group in ("containers", "initContainers"):
                            for container in doc["spec"].get(group, []):
                                yield path, group, container

    def test_every_app_container_has_one_exec_liveness(self):
        """Require agreed exec timing and literal commands for each app container."""
        count = 0
        for path, group, container in self.containers():
            if group == "initContainers":
                self.assertNotIn("startupProbe", container)
                self.assertNotIn("livenessProbe", container)
                self.assertNotIn("readinessProbe", container)
                continue
            count += 1
            with self.subTest(
                path=path.name, container=container["name"], probe="livenessProbe"
            ):
                probe = container["livenessProbe"]
                self.assertNotIn("httpGet", probe)
                self.assertNotIn("tcpSocket", probe)
                self.assertNotIn("readinessProbe", container)
                self.assertNotIn("startupProbe", container)
                self.assertEqual(probe["initialDelaySeconds"], 90)
                self.assertEqual(probe["periodSeconds"], 30)
                self.assertEqual(probe["timeoutSeconds"], 5)
                self.assertEqual(probe["failureThreshold"], 3)
                command = probe["exec"]["command"]
                self.assertTrue(command)
                self.assertTrue(all(isinstance(arg, str) for arg in command))
                self.assertNotIn("@@", " ".join(command))
        self.assertGreater(count, 0)

    def test_backend_probe_uses_livez_not_database_health(self):
        """Keep backend liveness separate from the database e2e endpoint."""
        backend = next(
            container
            for _, _, container in self.containers()
            if container["name"] == "backend"
        )
        command = " ".join(backend["livenessProbe"]["exec"]["command"])
        self.assertIn("127.0.0.1:8000/livez", command)
        self.assertNotIn("/api/health", command)

    def test_livez_is_anonymous_and_does_not_connect_to_database(self):
        """Execute liveness/auth functions without importing the app or its dependencies."""
        module = ast.parse((ROOT / "apps/todo-backend/app.py").read_text())
        functions = [
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef)
            and node.name in ("livez", "authenticate")
        ]
        self.assertEqual(len(functions), 2)
        namespace = {
            "request": types.SimpleNamespace(path="/livez", method="GET"),
            "session": {},
            "time": types.SimpleNamespace(time=lambda: 1),
            "abort": mock.Mock(side_effect=AssertionError("Authentication required")),
            "connect": mock.Mock(side_effect=AssertionError("Database accessed")),
        }
        for node in functions:
            node.decorator_list = []
        isolated = ast.parse("")
        isolated.body.extend(functions)
        exec(compile(isolated, "backend health functions", "exec"), namespace)  # noqa: S102
        namespace["authenticate"]()
        self.assertEqual(namespace["livez"](), ("", 204))
        namespace["abort"].assert_not_called()
        namespace["connect"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
