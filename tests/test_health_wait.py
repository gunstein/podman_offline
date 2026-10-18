"""install waits for running, healthy containers (backlog 34)."""

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from deployment import common, health

POD = {
    "kind": "Pod",
    "metadata": {"name": "app1-todo"},
    "spec": {
        "initContainers": [{"name": "prepare", "image": "localhost/a:1"}],
        "containers": [
            {"name": "backend", "image": "localhost/a:1"},
            {"name": "frontend", "image": "localhost/b:1"},
        ],
    },
}


class Clock:
    """A monotonic clock that sleep advances, so timeouts run instantly."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class WaitHealthyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "app1.yaml"
        self.path.write_text(yaml.safe_dump_all([{"kind": "Secret"}, POD]))
        self.clock = Clock()
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(
            mock.patch.object(health.time, "monotonic", self.clock.monotonic)
        )
        stack.enter_context(mock.patch.object(health.time, "sleep", self.clock.sleep))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def wait(self, states):
        """states: container name -> list of successive states (last one repeats)."""
        calls = []

        def state(name):
            calls.append(name)
            sequence = states[name]
            return sequence.pop(0) if len(sequence) > 1 else sequence[0]

        with mock.patch.object(health, "container_state", side_effect=state):
            health.wait_healthy("myproduct-app1.service", self.path)
        return calls

    def test_app_containers_only(self):
        self.assertEqual(
            health.expected_containers(self.path),
            ["app1-todo-backend", "app1-todo-frontend"],
        )

    def test_healthy_and_unchecked_containers_pass(self):
        calls = self.wait(
            {
                "app1-todo-backend": [("running", "healthy")],
                "app1-todo-frontend": [("running", "")],  # No health check.
            }
        )
        self.assertEqual(sorted(calls), ["app1-todo-backend", "app1-todo-frontend"])
        self.assertEqual(self.clock.now, 0)

    def test_starting_then_healthy_waits(self):
        self.wait(
            {
                "app1-todo-backend": [
                    None,
                    ("running", "starting"),
                    ("running", "healthy"),
                ],
                "app1-todo-frontend": [("running", "healthy")],
            }
        )
        self.assertEqual(self.clock.now, 2 * health.INTERVAL)

    def test_unhealthy_fails_at_once(self):
        with self.assertRaisesRegex(
            common.DeployError,
            "Container app1-todo-backend is unhealthy. Troubleshoot: journalctl "
            "--user -u myproduct-app1.service",
        ):
            self.wait(
                {
                    "app1-todo-backend": [("running", "unhealthy")],
                    "app1-todo-frontend": [("running", "healthy")],
                }
            )
        self.assertEqual(self.clock.now, 0)

    def test_exited_or_missing_containers_time_out_with_their_states(self):
        with self.assertRaisesRegex(
            common.DeployError,
            r"myproduct-app1.service is active, but after 150s these containers are "
            r"not running and healthy: app1-todo-backend \(exited\), "
            r"app1-todo-frontend \(missing\)",
        ):
            self.wait(
                {"app1-todo-backend": [("exited", "")], "app1-todo-frontend": [None]}
            )
        self.assertGreaterEqual(self.clock.now, health.TIMEOUT)


class ContainerStateTests(unittest.TestCase):
    def inspect(self, returncode=0, stdout=""):
        result = subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")
        with mock.patch.object(health.subprocess, "run", return_value=result) as run:
            state = health.container_state("app1-todo-backend")
        self.assertEqual(
            run.call_args.args[0],
            ["podman", "container", "inspect", "--format", "json", "app1-todo-backend"],
        )
        return state

    def test_states_from_inspect(self):
        self.assertEqual(
            self.inspect(
                stdout='[{"State": {"Status": "running", "Health": {"Status": "healthy"}}}]'
            ),
            ("running", "healthy"),
        )
        self.assertEqual(
            self.inspect(stdout='[{"State": {"Status": "running"}}]'), ("running", "")
        )
        self.assertIsNone(self.inspect(returncode=125))

    def test_unreadable_state_is_an_error_without_inspect_content(self):
        with self.assertRaisesRegex(
            common.DeployError,
            "^Unreadable podman inspect state for app1-todo-backend$",
        ):
            self.inspect(stdout='[{"Config": {"Env": ["SECRET=x"]}}]')


if __name__ == "__main__":
    unittest.main()
