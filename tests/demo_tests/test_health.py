"""Verify product probes and database-independent backend liveness without Podman."""

import ast
import types
import unittest
from pathlib import Path
from unittest import mock

import yaml
from deployment import render as rendering

from demo_tests.demo_fixture import DEMO_PUBLIC

ROOT = Path(__file__).resolve().parents[2]


class ProbeTests(unittest.TestCase):
    """Check the actual manifests and isolated backend health functions."""

    def containers(self):
        """Return every ordinary or init-container from product manifests."""
        for path in sorted((ROOT / "components").glob("*/manifests/*.yaml")):
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
                self.assertEqual(probe["initialDelaySeconds"], 10)
                self.assertEqual(probe["periodSeconds"], 10)
                self.assertEqual(probe["timeoutSeconds"], 5)
                self.assertEqual(probe["failureThreshold"], 6)
                config = rendering.merge_config(
                    path.parent.parent / "config.defaults.yaml", overrides=DEMO_PUBLIC
                )
                command = rendering.replace(probe["exec"]["command"], config)
                self.assertTrue(command)
                self.assertTrue(all(isinstance(arg, str) for arg in command))
                self.assertNotIn("@@", " ".join(str(arg) for arg in command))
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

    def test_backend_routes_and_cookie_are_scoped_to_the_app(self):
        """Keep auth/API routes and browser cookies independent for each Todo instance."""
        tree = ast.parse((ROOT / "apps/todo-backend/app.py").read_text())
        for component in ("app1", "app2"):
            namespace = {"BASE_PATH": "/" + component, "APP_ID": component}
            routes = []
            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    for decorator in node.decorator_list:
                        if (
                            isinstance(decorator, ast.Call)
                            and isinstance(decorator.func, ast.Attribute)
                            and decorator.func.attr
                            in ("get", "post", "patch", "delete")
                        ):
                            expression = ast.Expression(decorator.args[0])
                            routes.append(
                                eval(
                                    compile(expression, "backend route", "eval"),
                                    namespace,
                                )
                            )
            self.assertIn("/livez", routes)
            self.assertTrue(
                all(
                    route == "/livez" or route.startswith("/" + component + "/")
                    for route in routes
                )
            )
            settings = next(
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "update"
                and any(key.arg == "SESSION_COOKIE_PATH" for key in node.keywords)
            )
            cookies = {
                key.arg: eval(
                    compile(ast.Expression(key.value), "cookie setting", "eval"),
                    namespace,
                )
                for key in settings.keywords
                if key.arg in ("SESSION_COOKIE_NAME", "SESSION_COOKIE_PATH")
            }
            self.assertEqual(
                cookies,
                {
                    "SESSION_COOKIE_NAME": component + "-session",
                    "SESSION_COOKIE_PATH": "/" + component + "/",
                },
            )

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
            "BASE_PATH": "",
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
