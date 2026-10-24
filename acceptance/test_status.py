"""The lab checks actual status JSON against the independently transferred version."""

import contextlib
import copy
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import test_acceptance as base

REMOTE = Path(__file__).with_name("remote.sh").read_text()


class StatusProbeTests(unittest.TestCase):
    def report(self) -> dict:
        return {
            "product": "cedar",
            "pending": None,
            "components": [
                {
                    "name": "a-worker",
                    "version": "4.5.6",
                    "recorded_version": "4.5.6",
                    "unit": "cedar-a-worker.service",
                    "complete": True,
                    "state": "active",
                    "extra": "PrivateIgnoredData",
                }
            ],
        }

    def run_probe(self, data=None, failure=None):
        code = base.shell_code(REMOTE, heredoc="STATUS_REPORT")
        response = subprocess.CompletedProcess(
            [], 0, json.dumps(data or self.report()), "PrivateStderr"
        )
        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(
                    sys, "argv", ["probe", "/release", "cedar", "a-worker", "4.5.6"]
                )
            )
            process = stack.enter_context(
                mock.patch.object(
                    subprocess, "run", return_value=response, side_effect=failure
                )
            )
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            exec(compile(code, "STATUS_REPORT", "exec"), {})  # noqa: S102 - repository-owned probe
        self.assertEqual(
            process.call_args.args[0],
            ["bash", "/release/deploy.sh", "status", "--json"],
        )
        self.assertFalse(process.call_args.kwargs["check"])
        self.assertEqual(process.call_args.kwargs["timeout"], 90)
        return output.getvalue()

    def test_status_command_and_public_projection(self):
        output = self.run_probe()
        self.assertIn("PASS: installed component status", output)
        self.assertIn('"version": "4.5.6"', output)
        self.assertNotIn("Private", output)

    def test_wrong_version_product_pending_and_incomplete_states_fail(self):
        original = self.report()
        cases = []
        for key, value in (
            ("version", "1.0.0"),
            ("recorded_version", "9.0.0"),
            ("complete", False),
            ("state", "failed"),
            ("unit", "another-a-worker.service"),
            ("name", "another"),
        ):
            data = copy.deepcopy(original)
            data["components"][0][key] = value
            cases.append(data)
        for key, value in (
            ("product", "another"),
            ("pending", {"operation": "install"}),
            ("components", []),
        ):
            data = copy.deepcopy(original)
            data[key] = value
            cases.append(data)
        data = copy.deepcopy(original)
        data["components"].append(copy.deepcopy(data["components"][0]))
        cases.append(data)
        for data in cases:
            with (
                self.subTest(data=data),
                self.assertRaisesRegex(SystemExit, "status check; details withheld"),
            ):
                self.run_probe(data)

    def test_process_failures_are_reported_without_diagnostics(self):
        for failure in (
            OSError("PrivateError"),
            subprocess.TimeoutExpired("PrivateArgs", 90),
        ):
            with self.subTest(failure=type(failure).__name__):
                with self.assertRaises(SystemExit) as error:
                    self.run_probe(failure=failure)
                self.assertNotIn("Private", str(error.exception))

    def test_install_calls_status_only_after_success(self):
        helper = base.shell_code(REMOTE, function="install_checked")
        for result in (0, 7):
            script = (
                'product=/release\nas_product() { return "$1"; }\n'
                "status_release() { echo STATUS_CHECKED; }\n"
            )
            # as_product's first argument is python3, not the injected result.
            script = script.replace('return "$1"', "return " + str(result))
            completed = subprocess.run(
                ["bash", "-eu", "-c", script + helper + "\ninstall_checked"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, result, completed.stderr)
            self.assertEqual(
                completed.stdout.strip(), "STATUS_CHECKED" if result == 0 else ""
            )
        for action in (
            "install",
            "upgrade",
            "help-upgrade|platform-upgrade|identity-upgrade",
        ):
            self.assertIn("install_checked", base.shell_code(REMOTE, action=action))
